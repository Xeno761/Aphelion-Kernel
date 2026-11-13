#!/usr/bin/env bash
set -e

# ==========================================
# Fast Novatek Touch Driver & Vendor Boot Repacker
# ==========================================

WINDOWS_PROJECT_ROOT="/mnt/c/Users/Namit/Downloads/Aphelion-Kernel"
KERNEL_DIR="/root/Aphelion-Kernel"
OUT_DIR="/root/Aphelion-Kernel-out"
ARCH="arm64"

if [ -d "${WINDOWS_PROJECT_ROOT}/released" ]; then
    RELEASE_DIR="${WINDOWS_PROJECT_ROOT}/released"
else
    RELEASE_DIR="${KERNEL_DIR}/released"
fi

# Clang Toolchain Auto-detection
if [ -d "$HOME/toolchains/clang-r487747c/bin" ]; then
    CLANG_DIR="$HOME/toolchains/clang-r487747c/bin"
elif [ -d "/usr/lib/llvm-17/bin" ]; then
    CLANG_DIR="/usr/lib/llvm-17/bin"
else
    CLANG_DIR="/usr/bin"
fi
export PATH="${CLANG_DIR}:${PATH}"

CUSTOM_VBOOT=""
DO_FLASH=false
for arg in "$@"; do
    case "$arg" in
        --flash)
            DO_FLASH=true
            ;;
        *)
            if [ -f "$arg" ]; then
                CUSTOM_VBOOT="$(readlink -f "$arg")"
            fi
            ;;
    esac
done

echo "=================================================="
echo " Building Standalone NT36532 Driver & Repacking   "
echo "=================================================="

# 1. Verify Kernel Out Dir
if [ ! -d "${OUT_DIR}" ]; then
    echo "[-] ERROR: Kernel output directory ${OUT_DIR} not found!"
    echo "[-] Please run a baseline kernel build once so Module.symvers is generated."
    exit 1
fi

# 2. Compile NT36532 vendor module
echo "[*] Compiling NT36532 touch driver module..."
make -C "${OUT_DIR}" M="${KERNEL_DIR}/driver" CONFIG_TOUCHSCREEN_NT36xxx_HOSTDL_SPI=m ARCH="${ARCH}" LLVM=1 -j$(nproc) modules

MODULE_SRC="${KERNEL_DIR}/driver/nt36532.ko"
if [ ! -f "${MODULE_SRC}" ]; then
    echo "[-] ERROR: Compiled module ${MODULE_SRC} not found!"
    exit 1
fi

mkdir -p "${RELEASE_DIR}"
STRIPPED_MODULE="${RELEASE_DIR}/nt36532.ko"
llvm-strip --strip-unneeded -o "${STRIPPED_MODULE}" "${MODULE_SRC}"
sha256sum "${STRIPPED_MODULE}" > "${RELEASE_DIR}/nt36532.ko.sha256"
echo "[+] Stripped module created: ${STRIPPED_MODULE} ($(stat -c%s "${STRIPPED_MODULE}") bytes)"
echo "[+] SHA256: $(cat "${RELEASE_DIR}/nt36532.ko.sha256")"

# 3. Repack into vendor_boot.img
if [ -n "${CUSTOM_VBOOT}" ]; then
    VENDOR_BOOT_TEMPLATE="${CUSTOM_VBOOT}"
elif [ -f "${WINDOWS_PROJECT_ROOT}/images/vendor_boot.img" ]; then
    VENDOR_BOOT_TEMPLATE="${WINDOWS_PROJECT_ROOT}/images/vendor_boot.img"
elif [ -f "${KERNEL_DIR}/images/vendor_boot.img" ]; then
    VENDOR_BOOT_TEMPLATE="${KERNEL_DIR}/images/vendor_boot.img"
elif [ -f "./vendor_boot.img" ]; then
    VENDOR_BOOT_TEMPLATE="./vendor_boot.img"
else
    echo "[-] ERROR: vendor_boot.img template not found!"
    echo "[-] Usage: bash $0 [path/to/stock_vendor_boot.img] [--flash]"
    exit 1
fi
echo "[*] Using base vendor_boot: ${VENDOR_BOOT_TEMPLATE}"
KEY_FILE="${KERNEL_DIR}/Documentation/releases/testkey_rsa2048.pem"

echo "[*] Unpacking base vendor_boot.img..."
WORK_DIR=$(mktemp -d)
cd "${WORK_DIR}"
magiskboot unpack "${VENDOR_BOOT_TEMPLATE}" > /dev/null 2>&1 || true

if [ ! -f "./vendor_ramdisk/ramdisk.cpio" ]; then
    echo "[-] ERROR: vendor_ramdisk/ramdisk.cpio not found after unpack!"
    rm -rf "${WORK_DIR}"
    exit 1
fi

echo "[*] Injecting new nt36532.ko into vendor ramdisk..."
mkdir -p ./cpio_root
cd ./cpio_root
cpio -idm < ../vendor_ramdisk/ramdisk.cpio > /dev/null 2>&1

if [ ! -f "./lib/modules/nt36532.ko" ]; then
    echo "[-] ERROR: lib/modules/nt36532.ko not found in vendor ramdisk!"
    rm -rf "${WORK_DIR}"
    exit 1
fi

cp -p "${STRIPPED_MODULE}" ./lib/modules/nt36532.ko
find . | cpio -o -H newc > ../vendor_ramdisk/ramdisk.cpio 2> /dev/null
cd "${WORK_DIR}"
rm -rf ./cpio_root

echo "[*] Repacking vendor_boot image with magiskboot..."
magiskboot repack "${VENDOR_BOOT_TEMPLATE}" > /dev/null 2>&1 || true

if [ -f "${KEY_FILE}" ]; then
    echo "[*] Signing vendor_boot image with AVB test key..."
    avbtool erase_footer --image ./new-boot.img > /dev/null 2>&1 || true
    avbtool add_hash_footer --image ./new-boot.img --partition_name vendor_boot --partition_size 67108864 --key "${KEY_FILE}" --algorithm SHA256_RSA2048 > /dev/null 2>&1
fi

TARGET_VBOOT="${RELEASE_DIR}/vendor_boot.img"
cp -p ./new-boot.img "${TARGET_VBOOT}"
cd "${KERNEL_DIR}"
rm -rf "${WORK_DIR}"

sha256sum "${TARGET_VBOOT}" > "${RELEASE_DIR}/vendor_boot.img.sha256"
echo "[+] Flashable vendor_boot created: ${TARGET_VBOOT} ($(stat -c%s "${TARGET_VBOOT}") bytes)"
echo "[+] SHA256: $(cat "${RELEASE_DIR}/vendor_boot.img.sha256")"

# 4. Optional Live Flash via ADB
if [ "$DO_FLASH" = true ]; then
    echo "[*] Checking connected device for direct flashing..."
    ADB_CMD="/mnt/c/platform-tools/adb.exe"
    if [ ! -f "${ADB_CMD}" ]; then
        ADB_CMD="adb"
    fi
    DEV_STATE=$(${ADB_CMD} get-state 2>/dev/null | tr -d "\r\n" || echo "disconnected")
    if [ "$DEV_STATE" = "device" ]; then
        SLOT=$(${ADB_CMD} shell "getprop ro.boot.slot_suffix" | tr -d "\r\n")
        echo "[*] Active slot: ${SLOT}"
        echo "[*] Pushing vendor_boot.img to device..."
        ${ADB_CMD} push "${TARGET_VBOOT}" /data/local/tmp/vendor_boot.img
        echo "[*] Writing vendor_boot partition via dd (slot: ${SLOT})..."
        ${ADB_CMD} shell "su -c 'dd if=/data/local/tmp/vendor_boot.img of=/dev/block/by-name/vendor_boot${SLOT} bs=4096 conv=fsync && rm /data/local/tmp/vendor_boot.img'"
        echo "[+] vendor_boot${SLOT} flashed successfully!"
    else
        echo "[-] No ADB device connected in Android mode. Flash via fastboot:"
        echo "    fastboot flash vendor_boot ${TARGET_VBOOT}"
    fi
fi

echo "=================================================="
echo " Repack complete!                                 "
echo "=================================================="
