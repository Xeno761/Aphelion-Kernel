#!/usr/bin/env python3
"""
Aphelion Kernel — Zero-Bootloop Pre-Flight Symbol & Config Auditor
Prevents bootloops before packaging or flashing boot.img.

The module cross-check is mandatory: if no vendor module tree can be found, or
if the tooling needed to read it is unavailable, the audit FAILS. It must never
report success for a check it did not actually perform.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

# Directories searched, in order, when --modules / APHELION_MODULE_DIRS is not
# given. At least one must exist and contain .ko files.
DEFAULT_MODULE_DIRS = [
    "/root/module_inspect/vendor_ramdisk/lib/modules",
    "/mnt/c/Users/Namit/Downloads/Aphelion-Kernel/rev/dlkm/lib/modules",
    "/mnt/c/Users/Namit/Downloads/Aphelion-Kernel/rev/vb/rd/lib/modules",
]

TOOLCHAIN_NM = "/root/toolchains/clang-r487747c/bin/llvm-nm"

# Symbols already known to be unresolved against this kernel, recorded so the
# audit is a ratchet: a NEW unresolved symbol fails the build, a known one is
# reported. Regenerate deliberately when a gap is understood and accepted.
BASELINE_NAME = "vendor_symbol_baseline.txt"

# Options that must stay off: they cost performance and none of them is needed
# to boot a production kernel.
EXPECTED_OFF = ["CONFIG_SLUB_DEBUG", "CONFIG_WQ_WATCHDOG", "CONFIG_PM_DEBUG"]


def find_nm():
    """Prefer the build toolchain's llvm-nm, fall back to PATH."""
    if os.access(TOOLCHAIN_NM, os.X_OK):
        return TOOLCHAIN_NM
    found = shutil.which("llvm-nm")
    if found:
        return found
    return None


def resolve_module_dirs(extra):
    """Return the module directories that actually exist, or []."""
    if extra:
        candidates = extra
    else:
        env = os.environ.get("APHELION_MODULE_DIRS")
        candidates = env.split(os.pathsep) if env else DEFAULT_MODULE_DIRS
    return [d for d in candidates if os.path.isdir(d)]


def collect_modules(dirs):
    mods = []
    for d in dirs:
        mods.extend(sorted(glob.glob(os.path.join(d, "*.ko"))))
    return mods


def config_checks(config_file, errors):
    if not os.path.exists(config_file):
        errors.append("Missing kernel .config at %s" % config_file)
        return

    with open(config_file) as f:
        cfg = f.read()

    if "CONFIG_MODULE_SIG_SHA1=y" not in cfg:
        errors.append("VIOLATION (Section 6.10): CONFIG_MODULE_SIG_SHA1=y is NOT enabled! "
                      "Lenovo vendor modules are signed with SHA-1.")

    if 'CONFIG_MODULE_SIG_HASH="sha1"' not in cfg:
        errors.append('VIOLATION (Section 6.10): CONFIG_MODULE_SIG_HASH is not set to "sha1"!')

    if "rcu_nocbs=all" in cfg:
        errors.append("VIOLATION (Section 6.11): rcu_nocbs=all detected in CONFIG_CMDLINE! "
                      "This causes early boot lockup.")

    if "CONFIG_ZERO_CALL_USED_REGS=y" in cfg:
        errors.append("VIOLATION (Section 6.12): CONFIG_ZERO_CALL_USED_REGS=y detected! "
                      "May alter vendor module register state.")

    for opt in EXPECTED_OFF:
        if "%s=y" % opt in cfg:
            errors.append("VIOLATION (perf): %s=y is still enabled; it was requested off." % opt)


def load_baseline(script_dir):
    path = os.path.join(script_dir, BASELINE_NAME)
    if not os.path.exists(path):
        return set(), path
    syms = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                syms.add(line)
    return syms, path


def symbol_check(symvers_file, module_dirs, errors, baseline):
    """Cross-check every undefined symbol in every vendor module."""
    if not os.path.exists(symvers_file):
        errors.append("Missing vmlinux.symvers at %s" % symvers_file)
        return False

    nm = find_nm()
    if nm is None:
        errors.append("Cannot cross-check vendor modules: no llvm-nm found "
                      "(looked for %s and PATH)." % TOOLCHAIN_NM)
        return False

    if not module_dirs:
        errors.append("Cannot cross-check vendor modules: no vendor module directory exists. "
                      "Searched: %s (override with --modules DIR or APHELION_MODULE_DIRS)."
                      % ", ".join(DEFAULT_MODULE_DIRS))
        return False

    modules = collect_modules(module_dirs)
    if not modules:
        errors.append("Cannot cross-check vendor modules: no .ko files under %s."
                      % ", ".join(module_dirs))
        return False

    vmlinux_syms = set()
    with open(symvers_file) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                vmlinux_syms.add(parts[1])

    print("[*] Loaded %d exported symbols from %s" % (len(vmlinux_syms), symvers_file))
    for d in module_dirs:
        print("[*]   module dir: %s" % d)
    print("[*] Auditing symbol resolution across %d vendor modules..." % len(modules))

    undef_syms = set()
    mod_exported = set()
    unreadable = []

    for m in modules:
        res = subprocess.run([nm, "-g", m], capture_output=True, text=True)
        if res.returncode != 0:
            unreadable.append(os.path.basename(m))
            continue
        for line in res.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[0] == "U":
                undef_syms.add(parts[1])
            elif len(parts) >= 3 and parts[1] in ("T", "D", "B", "R", "W", "V"):
                mod_exported.add(parts[2])

    if unreadable:
        errors.append("Could not read %d of %d vendor modules (%s) — the cross-check "
                      "is incomplete." % (len(unreadable), len(modules),
                                          ", ".join(unreadable[:5])))

    missing = undef_syms - vmlinux_syms - mod_exported
    known = missing & baseline
    new = missing - baseline

    from_vmlinux = len(undef_syms & vmlinux_syms)
    print("[*] %d distinct undefined symbols; %d resolve from vmlinux, "
          "%d via other modules, %d unresolved (%d baseline, %d new)"
          % (len(undef_syms), from_vmlinux,
             len(undef_syms & mod_exported - vmlinux_syms),
             len(missing), len(known), len(new)))

    if known:
        print("[*] %d known-unresolved symbol(s) from the baseline (not fatal):" % len(known))
        for s in sorted(known):
            print("      . %s" % s)

    stale = baseline - missing - vmlinux_syms
    if stale:
        print("[!] %d baseline entr(ies) no longer unresolved; prune the baseline: %s"
              % (len(stale), ", ".join(sorted(stale)[:10])))

    for s in sorted(new):
        errors.append("FATAL MISSING SYMBOL: '%s' is required by vendor modules but missing "
                      "from vmlinux! Bootloop guaranteed." % s)

    return not unreadable


def main():
    print("==================================================")
    print("   Aphelion Pre-Flight Zero-Bootloop Symbol Audit  ")
    print("==================================================")

    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir", nargs="?", default="/root/Aphelion-Kernel-out")
    ap.add_argument("--modules", action="append", default=[],
                    help="vendor module directory (repeatable)")
    args = ap.parse_args()

    symvers_file = os.path.join(args.out_dir, "vmlinux.symvers")
    config_file = os.path.join(args.out_dir, ".config")

    errors = []
    config_checks(config_file, errors)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    baseline, baseline_path = load_baseline(script_dir)
    print("[*] Baseline: %d symbol(s) from %s"
          % (len(baseline), baseline_path if os.path.exists(baseline_path) else "(none)"))
    checked = symbol_check(symvers_file, resolve_module_dirs(args.modules), errors, baseline)

    if errors:
        print("\n[-] PRE-FLIGHT AUDIT FAILED! The kernel MUST NOT be flashed:")
        for err in errors:
            print("    - %s" % err)
        print("==================================================")
        sys.exit(1)

    if not checked:
        # Unreachable by construction, but never let a skipped check pass.
        print("\n[-] PRE-FLIGHT AUDIT FAILED: symbol cross-check did not run.")
        sys.exit(1)

    print("\n[+] PRE-FLIGHT AUDIT PASSED: vendor module symbols cross-checked "
          "and config constraints verified.")
    print("==================================================")
    sys.exit(0)


if __name__ == "__main__":
    main()
