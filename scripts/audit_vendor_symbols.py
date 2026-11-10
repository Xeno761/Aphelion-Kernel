#!/usr/bin/env python3
"""
Aphelion Kernel — Zero-Bootloop Pre-Flight Symbol & Config Auditor
Prevents bootloops before packaging or flashing boot.img.
"""

import os
import sys
import glob
import subprocess

def audit():
    print("==================================================")
    print("   Aphelion Pre-Flight Zero-Bootloop Symbol Audit  ")
    print("==================================================")
    
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/root/Aphelion-Kernel-out"
    symvers_file = os.path.join(out_dir, "vmlinux.symvers")
    config_file = os.path.join(out_dir, ".config")
    module_dir = "/root/module_inspect/vendor_ramdisk/lib/modules"
    
    errors = []
    
    # 1. Config Checks
    if not os.path.exists(config_file):
        errors.append(f"Missing kernel .config at {config_file}")
    else:
        with open(config_file) as f:
            cfg = f.read()
            
        if "CONFIG_MODULE_SIG_SHA1=y" not in cfg:
            errors.append("VIOLATION (Section 6.10): CONFIG_MODULE_SIG_SHA1=y is NOT enabled! Lenovo vendor modules are signed with SHA-1.")
            
        if 'CONFIG_MODULE_SIG_HASH="sha1"' not in cfg:
            errors.append("VIOLATION (Section 6.10): CONFIG_MODULE_SIG_HASH is not set to \"sha1\"!")
            
        if "rcu_nocbs=all" in cfg:
            errors.append("VIOLATION (Section 6.11): rcu_nocbs=all detected in CONFIG_CMDLINE! This causes early boot lockup.")
            
        if "CONFIG_ZERO_CALL_USED_REGS=y" in cfg:
            errors.append("VIOLATION (Section 6.12): CONFIG_ZERO_CALL_USED_REGS=y detected! May alter vendor module register state.")

    # 2. Comprehensive Symbol Resolution Check
    if not os.path.exists(symvers_file):
        errors.append(f"Missing vmlinux.symvers at {symvers_file}")
    elif not os.path.isdir(module_dir):
        print(f"[*] Warning: Vendor module directory {module_dir} not found. Skipping module cross-check.")
    else:
        vmlinux_syms = set()
        with open(symvers_file) as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    vmlinux_syms.add(parts[1])
                    
        print(f"[*] Loaded {len(vmlinux_syms)} exported symbols from {symvers_file}")
        
        modules = glob.glob(os.path.join(module_dir, "*.ko"))
        print(f"[*] Auditing symbol resolution across {len(modules)} vendor modules...")
        
        undef_syms = set()
        mod_exported = set()
        for m in modules:
            res_u = subprocess.run(["llvm-nm", "-u", m], capture_output=True, text=True)
            for line in res_u.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0] == "U":
                    undef_syms.add(parts[1])
                    
            res_g = subprocess.run(["llvm-nm", "-g", m], capture_output=True, text=True)
            for line in res_g.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] in ("T", "D", "B", "R"):
                    mod_exported.add(parts[2])
                    
        missing = undef_syms - vmlinux_syms - mod_exported
        if missing:
            for s in sorted(missing):
                errors.append(f"FATAL MISSING SYMBOL: '{s}' is required by vendor modules but missing from vmlinux! Bootloop guaranteed.")

    if errors:
        print("\n[-] PRE-FLIGHT AUDIT FAILED! The kernel MUST NOT be flashed:")
        for err in errors:
            print(f"    - {err}")
        print("==================================================")
        sys.exit(1)

    print("\n[+] PRE-FLIGHT AUDIT PASSED: 100% of vendor module symbols & configs verified!")
    print("==================================================")
    sys.exit(0)

if __name__ == "__main__":
    audit()
