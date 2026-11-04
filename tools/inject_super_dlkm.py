#!/usr/bin/env python3
import sys
import os

SECTOR_SIZE = 512
DLKM_START_SECTOR = 16717824      # Sector offset inside super.img
DLKM_BYTE_OFFSET = DLKM_START_SECTOR * SECTOR_SIZE # 0x1fe300000 (8,559,525,888 bytes)
DLKM_PARTITION_SIZE = 20316160   # 39680 sectors (19,840 KiB)

def inject(super_path, dlkm_path):
    if not os.path.exists(super_path):
        print(f"Error: super.img not found at {super_path}")
        sys.exit(1)
    if not os.path.exists(dlkm_path):
        print(f"Error: vendor_dlkm.img not found at {dlkm_path}")
        sys.exit(1)

    dlkm_size = os.path.getsize(dlkm_path)
    if dlkm_size > DLKM_PARTITION_SIZE:
        print(f"Error: vendor_dlkm.img ({dlkm_size} bytes) exceeds allocated partition size ({DLKM_PARTITION_SIZE} bytes)")
        sys.exit(1)

    print(f"[*] Reading vendor_dlkm payload: {dlkm_path} ({dlkm_size} bytes)...")
    with open(dlkm_path, "rb") as f:
        data = f.read()

    if len(data) < DLKM_PARTITION_SIZE:
        pad = DLKM_PARTITION_SIZE - len(data)
        print(f"[*] Padding payload with {pad} zero bytes...")
        data += b"\x00" * pad

    print(f"[*] Injecting vendor_dlkm into {super_path} at offset 0x{DLKM_BYTE_OFFSET:X} (sector {DLKM_START_SECTOR})...")
    with open(super_path, "r+b") as f:
        f.seek(DLKM_BYTE_OFFSET)
        f.write(data)

    print("[+] Successfully injected vendor_dlkm into super.img without disturbing LP metadata!")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 inject_super_dlkm.py <path_to_super.img> <path_to_vendor_dlkm.img>")
        sys.exit(1)
    inject(sys.argv[1], sys.argv[2])
