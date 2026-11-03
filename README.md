# TB373FU NT36532 Touch Driver

Experimental prerelease for **Lenovo Idea Tab Pro / TB373FU (MT6897) only**. Not for other device variants or other NT36xx controllers. This exact build has not been boot-tested on hardware.

This is a reliability update, not a sensitivity adjustment or a cure for faulty hardware. Input devices are `NVTCapacitiveTouchScreen` and `touch-pen`.

**Prebuilt target: TB373FU with the matching [Aphelion v1.1.0 kernel](https://github.com/Xeno761/Aphelion-Kernel/releases/tag/v1.1.0). These binaries are NOT compatible with Lenovo's stock kernel.**

The module was built against the 6.1.148 Aphelion configuration and checked against the `6.1.182-aphelion-v1.1.0` kernel image below. Its 135 import versions and six exported interfaces passed the symbol checks. This is not a claim that every firmware combination or physical ABI detail has been validated.

| Reference | SHA-256 |
| --- | --- |
| Aphelion v1.1.0 `boot.img` | `7d15a84df04788dbc0bad198340ab151e7766428f63c3cacd0e815545be5b728` |
| Stock `vendor_boot` used as the carrier | `df37fbe685847270c71fd315606205596dfc6a51c1c8d20b865c75bf64f15494` |

The carrier's other 222 modules, DTB, recovery fragment and bootconfig are unchanged. The replacement module is still an Aphelion-ABI build: its module layout is 1024 bytes with CRC `0xc60093cd`, while the stock module uses 1088 bytes and CRC `0xea759d7f`. Changing a version string or checksum cannot make those layouts compatible.

Same hardware is not enough. Kernel ABI, configuration, module versions, vendor symbol providers and module-signing policy must match. Repacking a module into your own image does **not** make an incompatible module loadable. A stock-kernel installation needs a separate matching build and ABI validation, not these prebuilt binaries.

## Changes

- Bounded recovery for repeated `0x77` handshakes and watchdog faults, with one shared cooldown and incident cap rather than repeated reset loops.
- Passive health checks using the `0xA2..0xAF` reset-state range. Silence alone is not a reset trigger; a readable state is not proof that scanning is healthy.
- The original 14-second cold-boot firmware delay is preserved. Delayed-work scheduling uses a consistent time sample to avoid subtraction underflow.
- Firmware readiness and command restoration are checked; SPI/raw-buffer bounds and locking are tightened, with rate-limited fault logs.
- Root can read `/proc/nvt_health` for diagnostics. This node is read-only, not a tuning interface.

## Files

Download assets and `SHA256SUMS` from the [touch-driver release](https://github.com/Xeno761/Aphelion-Kernel/releases/tag/nt36532-tb373fu-v1).

- `vendor_boot.img`: stock-carrier image with only the touchscreen module replaced, for the release-bound kernel and firmware only.
- `nt36532.ko`: driver module for offline repacking into a compatible image.
- This source branch contains `driver/`, host tests in `tests/`, and `tools/repack_vendor_boot.py`.

## Before Installing

A wrong image or module can **bootloop the tablet or disable touch and pen input**. Both methods below have the same device and ABI requirements.

1. Keep a verified PC backup of the working `vendor_boot_a` partition for your current firmware and active slot `a`. Use recovery or an already-authorized rooted system to create a backup file, transfer it with `adb pull`, and compare its PC SHA-256 with the device-side SHA-256. Keep it off the tablet as `vendor_boot_a.backup.img`. These instructions deliberately cover only verified active slot `a`; stop on another slot.
2. Confirm hardware-key access to the bootloader/recovery and a working route to **fastbootd** without touch input. The bootloader must already permit the intended image. Do not proceed without a tested rollback route.
3. Verify the release checksums and exact kernel/firmware binding. Do not patch CRCs or vermagic, force-load a module, or disable verification to bypass a mismatch.

**All commands below use Linux/WSL Bash**, with working Android platform-tools and USB access. Do not capture raw partition stdout with Windows PowerShell redirection; use a device-side file and `adb pull` for backups.

Enter fastbootd and check the target, mode and slot:

```bash
adb reboot fastboot
fastboot devices
fastboot getvar product
fastboot getvar is-userspace
fastboot getvar current-slot
```

Proceed only for your TB373FU with **`is-userspace: yes`** and **`current-slot: a`**, matching the backup. Use fastbootd, as required by the matching kernel's installation procedure, not ordinary bootloader-fastboot. Stop if a check differs; do not switch slots. Never flash both slots, and do not flash `boot`, `init_boot` or `vbmeta` as part of these instructions.

## Method 1: Prebuilt

This replaces the whole `vendor_boot` image and is the riskier option. Use it only when your kernel **and firmware** match the release binding exactly; a matching model name is insufficient.

```bash
sha256sum vendor_boot.img nt36532.ko
# Compare both digests with the release page before continuing.
fastboot flash vendor_boot_a vendor_boot.img && fastboot reboot
```

## Method 2: Repack Your Own Image

Preferred: start with your own exact stock/ROM `vendor_boot` backup for the installed firmware, and replace only its existing `lib/modules/nt36532.ko`. The supplied module must still match your running kernel. In particular, using a stock image as a carrier does not make this prebuilt module stock-kernel compatible.

Use Python 3.9+, the `lz4` executable, and the official [AOSP mkbootimg tools](https://android.googlesource.com/platform/system/tools/mkbootimg/) from an appropriate kernel/ROM tool tree. Set `KERNEL_TOOLS` to the directory containing `mkbootimg.py` and `unpack_bootimg.py`, with their dependencies intact. `--lz4 /path/to/lz4` can select an executable explicitly; otherwise it is found on `PATH`.

```bash
python3 tools/repack_vendor_boot.py \
  --device TB373FU \
  --base vendor_boot_a.backup.img \
  --module nt36532.ko \
  --output vendor_boot.repacked.img \
  --work repack-work \
  --kernel-tools "$KERNEL_TOOLS"
```

The work directory and output must not exist; their parents must already exist. The tool never installs anything or contacts the tablet. It supports only the known unsigned vendor_boot v4 layout with two fragments, platform then recovery, a legacy-LZ4 platform ramdisk, and `newc` CPIO. It refuses missing/duplicate targets, malformed archives, unknown layouts, AVB footers and nonzero extra metadata. It cannot sign images or handle AVB; a separate vbmeta descriptor covering a footerless image is also outside its checks. Do not strip signing metadata to get past a refusal.

Before producing the output it requires a byte-identical unmodified image roundtrip, preserves other CPIO entries and their metadata/order, verifies DTB/recovery/bootconfig, and keeps the original image size. It writes a hash/check manifest inside the work directory. **Successful packaging is not ABI validation or proof of a successful boot.**

After all checks pass and the compatibility requirements are satisfied:

```bash
fastboot getvar is-userspace
fastboot getvar current-slot
# Proceed only for is-userspace: yes and current-slot: a, matching the backup.
fastboot flash vendor_boot_a vendor_boot.repacked.img && fastboot reboot
```

## Rollback

If boot or input fails, use the hardware keys and the ROM's recovery procedure to reach fastbootd. Recheck the target and slot, then restore the verified backup for that same modified slot and firmware:

```bash
fastboot devices
fastboot getvar product
fastboot getvar is-userspace
fastboot getvar current-slot
# Proceed only for your TB373FU, is-userspace: yes and current-slot: a.
fastboot flash vendor_boot_a vendor_boot_a.backup.img && fastboot reboot
```

If the bootloader switched slots, stop and use the ROM's documented recovery procedure to identify the affected slot. Do not restore a backup to a different slot, switch slots blindly, or overwrite other boot partitions.

## Building

This is an external-module example, not a turnkey kernel build. Use your exact matching prepared kernel source/output, generated headers, `.config`, `Module.symvers`, vendor headers/export symvers and Clang toolchain. `modules_prepare` alone does not supply the symbol CRCs needed for a modversioned kernel.

Set `KERNEL_SRC`, `KERNEL_OUT`, `DEVICE_MODULES` and `VENDOR_SYMVERS` to those matching inputs, and put the matching Clang tools on `PATH`. From this branch's root:

```bash
make -C "$KERNEL_SRC" O="$KERNEL_OUT" M="$PWD/driver" \
  ARCH=arm64 LLVM=1 CONFIG_TOUCHSCREEN_NT36xxx_HOSTDL_SPI=m \
  KCONFIG_EXT_PREFIX="$DEVICE_MODULES/" \
  DEVICE_MODULES_PATH="$DEVICE_MODULES" \
  EXTRA_CFLAGS="-I$DEVICE_MODULES/include" \
  KBUILD_EXTRA_SYMBOLS="$VENDOR_SYMVERS" modules
```

The output is `driver/nt36532.ko`. Validate its imports, exports, module layout, configuration and version/signing requirements against the intended running kernel and vendor modules before repacking. Do not modify symbol CRCs to make a check pass.

## Tests And License

The driver host suite has passed 71 cases with both `cc` and Clang. The portable repacker has 9 focused host tests using synthetic images and mocked external tools. The release image was also checked for an unchanged base roundtrip and preservation of every non-target payload. Host SPI/IRQ/workqueue/locking mocks do not validate real IRQ concurrency, electrical behavior or hardware boot reliability.

```bash
NT36532_SOURCE_DIR="$PWD/driver" NT36532_CC=cc python3 -B -m unittest discover -s tests -p 'test_nt36532_*.py' -v
NT36532_SOURCE_DIR="$PWD/driver" NT36532_CC=clang python3 -B -m unittest discover -s tests -p 'test_nt36532_*.py' -v
python3 -B -m unittest discover -s tests -p 'test_repack_vendor_boot.py' -v
```

Keep the upstream copyright and attribution notices in the driver files. The driver remains under its existing GPLv2 terms; distribute the corresponding source and build information with binaries. The new repacker/tests are GPL-2.0-only. AOSP tools retain their own licenses.
