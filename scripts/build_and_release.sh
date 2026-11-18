#!/usr/bin/env bash
set -e

# ==========================================
# Configuration & Paths
# ==========================================
WINDOWS_PROJECT_ROOT="/mnt/c/Users/Namit/Downloads/Aphelion-Kernel"
RELEASE_DIR="${WINDOWS_PROJECT_ROOT}/released"
KERNEL_DIR="/root/Aphelion-Kernel"
OUT_DIR="/root/Aphelion-Kernel-out"
DEFCONFIG="${DEFCONFIG:-aphelion_defconfig}"
ARCH="arm64"
SUBARCH="arm64"

# Use the vendor-validated AOSP compiler, never silently fall back.
CLANG_DIR="$HOME/toolchains/clang-r487747c/bin"
if [ ! -x "${CLANG_DIR}/clang" ]; then
    echo "[-] Required AOSP Clang r487747c is missing."
    exit 1
fi
export PATH="${CLANG_DIR}:${PATH}"

# Check for flags
PRUNE_OUT=false
for arg in "$@"; do
    case $arg in
        --prune|--prune-out)
            PRUNE_OUT=true
            ;;
        --defconfig=*)
            DEFCONFIG="${arg#*=}"
            ;;
    esac
done

echo "=========================================="
echo " Starting Optimized Kernel Build via WSL  "
echo "=========================================="
echo "[*] Kernel Source : ${KERNEL_DIR}"
echo "[*] Output Dir    : ${OUT_DIR}"
echo "[*] Toolchain     : ${CLANG_DIR} ($(clang --version | head -n 1))"
echo "[*] Defconfig     : ${DEFCONFIG}"
echo "[*] Architecture  : ${ARCH}"

# 1. Setup ccache configuration
export CCACHE_DIR="$HOME/.ccache"
export CCACHE_MAXSIZE="40G"
ccache -M 40G > /dev/null 2>&1
ccache -o compression=true > /dev/null 2>&1
ccache -o sloppiness=file_macro,time_macros,include_file_mtime,include_file_ctime > /dev/null 2>&1

# 2. Stable build identity preserves reproducibility and ccache hits.
export TZ='Asia/Kolkata'
export KBUILD_BUILD_TIMESTAMP="${KBUILD_BUILD_TIMESTAMP:-}"
export KBUILD_BUILD_USER='builder'
export KBUILD_BUILD_HOST='wsl'
export ARCH="${ARCH}"
export SUBARCH="${SUBARCH}"

cd "${KERNEL_DIR}"

# 3. Create out directory
mkdir -p "${OUT_DIR}"

# 4. Generate defconfig and ensure non-interactive olddefconfig
echo "[*] Applying config: ${DEFCONFIG}..."
make ARCH="${ARCH}" LLVM=1 O="${OUT_DIR}" "${DEFCONFIG}"
make ARCH="${ARCH}" LLVM=1 O="${OUT_DIR}" olddefconfig

# 5. Compile Kernel Image with all available CPU threads
echo "[*] Compiling Kernel Image with Kbuild & ccache (-j$(nproc))..."
make -j$(nproc) ARCH="${ARCH}" LLVM=1 O="${OUT_DIR}" CC="ccache clang" Image

# 6. Verification Step
TARGET_IMAGE="${OUT_DIR}/arch/arm64/boot/Image"
if [ ! -f "${TARGET_IMAGE}" ]; then
    echo "[-] ERROR: Kernel Image failed to compile!"
    exit 1
fi
echo "[+] Compilation successful: ${TARGET_IMAGE}"
echo "[*] ccache Statistics:"
ccache -s | head -n 8

# 6.5 Zero-Bootloop Pre-Flight Symbol & Config Audit
if [ -f "${KERNEL_DIR}/scripts/audit_vendor_symbols.py" ]; then
    python3 "${KERNEL_DIR}/scripts/audit_vendor_symbols.py" "${OUT_DIR}" \
        --modules /root/inspect_modules/lib/modules \
        --modules /root/inspect_modules/vendor_dlkm_stock/lib/modules \
        --modules /root/inspect_modules/system_dlkm_stock/lib/modules
else
    echo "[-] Mandatory vendor-module audit script is missing."
    exit 1
fi

# 7. Verify the signed image before replacing the current release.
BOOT_TEMPLATE="${WINDOWS_PROJECT_ROOT}/images/boot.img"
KEY_FILE="${KERNEL_DIR}/Documentation/releases/testkey_rsa2048.pem"
if [ ! -f "${BOOT_TEMPLATE}" ] || [ ! -f "${KEY_FILE}" ]; then
    echo "[-] Required boot template or AVB signing key is missing."
    exit 1
fi
WORK_DIR=$(mktemp -d)
trap 'rm -rf "${WORK_DIR}"' EXIT
cd "${WORK_DIR}"
magiskboot unpack "${BOOT_TEMPLATE}"
cp -p "${TARGET_IMAGE}" ./kernel
magiskboot repack "${BOOT_TEMPLATE}"
avbtool erase_footer --image ./new-boot.img > /dev/null 2>&1 || true
avbtool add_hash_footer --image ./new-boot.img --partition_name boot --partition_size 67108864 \
    --key "${KEY_FILE}" --algorithm SHA256_RSA2048
mv ./new-boot.img ./boot.img
avbtool verify_image --image ./boot.img --key "${KEY_FILE}"
magiskboot unpack ./boot.img
cmp "${TARGET_IMAGE}" ./kernel

# Release & Storage Synchronization
echo "[*] Synchronizing to Windows release directory..."
mkdir -p "${RELEASE_DIR}"

# Wipe old released build to prevent disk waste
find "${RELEASE_DIR}" -maxdepth 1 -type f ! -name "*.zip" -delete

# Copy new verified raw kernel and config
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
cp -p "${TARGET_IMAGE}" "${RELEASE_DIR}/Image"
cp -p "${OUT_DIR}/.config" "${RELEASE_DIR}/build_config_${TIMESTAMP}.config"
cp -p "${WORK_DIR}/boot.img" "${RELEASE_DIR}/boot.img"
cd "${RELEASE_DIR}"
sha256sum "build_config_${TIMESTAMP}.config" > "build_config_${TIMESTAMP}.config.sha256"
sha256sum boot.img > boot.img.sha256
sha256sum Image > Image.sha256
cd "${KERNEL_DIR}"

# 8. Kbuild Optimization vs. Optional Storage Cleanup
if [ "$PRUNE_OUT" = true ]; then
    echo "[*] --prune requested: Pruning intermediate object files from out/..."
    find "${OUT_DIR}" -name "*.o" -delete
    find "${OUT_DIR}" -name "*.cmd" -delete
    echo "[+] Intermediate .o and .cmd files pruned to save disk space."
else
    echo "[*] KBUILD PRESERVATION ACTIVE: Preserving .o and .cmd files in ${OUT_DIR}."
    echo "[*] Incremental builds for code edits will take ~5-15 seconds!"
    echo "[*] (Pass --prune if you ever want to free intermediate disk space)."
fi

echo "=========================================="
echo " Done! Active release updated in Windows: "
echo " ${RELEASE_DIR} "
echo "=========================================="
