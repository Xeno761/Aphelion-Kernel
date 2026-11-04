#!/usr/bin/env bash
# Repack vendor_dlkm EROFS image with strict Android SELinux security contexts
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <extracted_tree_dir> <output_vendor_dlkm.img> [target_size_bytes]"
    echo "Example: $0 /path/to/extracted_tree vendor_dlkm.repacked.img 20316160"
    exit 1
fi

SRC_DIR="$1"
OUT_IMG="$2"
TARGET_SIZE="${3:-20316160}"

if ! command -v mkfs.erofs &> /dev/null; then
    echo "Error: mkfs.erofs is required. Install erofs-utils."
    exit 1
fi

TMP_FC="$(mktemp)"
trap 'rm -f "$TMP_FC"' EXIT

# Generate SELinux file contexts matching Android standard vendor partition specification
cat << 'FC' > "$TMP_FC"
/ u:object_r:vendor_file:s0
/.* u:object_r:vendor_file:s0
/etc(/.*)? u:object_r:vendor_configs_file:s0
/lib(/.*)? u:object_r:vendor_file:s0
/lib/modules(/.*)? u:object_r:vendor_file:s0
FC

echo "[+] Building EROFS vendor_dlkm filesystem with SELinux xattrs..."
mkfs.erofs -b 4096 -z lz4hc,12 \
    -U 9075e177-827b-45fa-8a12-191ceec856e1 \
    -T 1719456000 \
    --file-contexts="$TMP_FC" \
    --all-root \
    "$OUT_IMG" "$SRC_DIR"

ACTUAL_SIZE=$(stat -c %s "$OUT_IMG")
echo "[+] Raw EROFS size: $ACTUAL_SIZE bytes"

if [ "$ACTUAL_SIZE" -gt "$TARGET_SIZE" ]; then
    echo "Error: Image size ($ACTUAL_SIZE) exceeds target partition size ($TARGET_SIZE)"
    exit 1
fi

if [ "$ACTUAL_SIZE" -lt "$TARGET_SIZE" ]; then
    PAD_BYTES=$((TARGET_SIZE - ACTUAL_SIZE))
    echo "[+] Padding $PAD_BYTES zero bytes to match exact LP extent boundary ($TARGET_SIZE bytes)..."
    python3 -c "with open('$OUT_IMG', 'ab') as f: f.write(b'\x00' * $PAD_BYTES)"
fi

FINAL_SIZE=$(stat -c %s "$OUT_IMG")
echo "[+] Successfully generated $OUT_IMG ($FINAL_SIZE bytes)"
