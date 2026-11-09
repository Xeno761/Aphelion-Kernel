<div align="center">

# Aphelion Kernel

### Lenovo Idea Tab Pro | TB373FU | MT6897 (Dimensity 8300)

[![Release](https://img.shields.io/github/v/release/Xeno761/Aphelion-Kernel?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/releases/latest)
[![Source](https://img.shields.io/badge/Source-aphelion--public-blue?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/tree/aphelion-public)
[![License](https://img.shields.io/badge/License-GPL--2.0-green?style=flat-square)](COPYING)

[Download](https://github.com/Xeno761/Aphelion-Kernel/releases/latest) | [Installation](#installation) | [Documentation](Documentation/) | [Changelog](https://github.com/Xeno761/Aphelion-Kernel/commits/aphelion-public)

</div>

## Overview

**Aphelion Kernel** is a high-performance, KMI-compliant Android 14 GKI kernel customized for the **Lenovo Idea Tab Pro (TB373FU)** powered by the MediaTek MT6897 (Dimensity 8300) SoC.

The kernel tree is aligned directly with Google's official Android Common Kernel (ACK) **`android14-6.1-lts`**, ensuring full alignment with Android's frozen Kernel Module Interface (KMI) and ABI compatibility with stock MediaTek vendor modules (`.ko`).

## Build Information

| Component | Details |
| --- | --- |
| Target Device | Lenovo Idea Tab Pro (TB373FU / MT6897) |
| Architecture | ARM64 (`aarch64`) |
| Base Tree | Google ACK `android14-6.1-lts` |
| Toolchain | Google AOSP Clang 17 (`clang-r487747c` / LLVM 17.0.2) |
| Status | Verified on-device (TB373FU); all 475 vendor modules active |
| Shipped Asset | `boot.img` only |

> [!NOTE]
> The source preserves strict KMI boundary compatibility: core exported struct sizes in `include/linux/` remain unaltered. Task and namespace additions utilize Android KABI reserved fields (`ANDROID_KABI_RESERVE`).

---

## Added Over Stock

### 1. Root and Kernel Security
- **ReSukiSU / BakaSU:** Embedded with SUSFS inline hooks (`sus_path`, `sus_mount`, `sus_kstat`, `sus_map`).
- **Multi-Manager Certificate Recognition:** Native support for Official KernelSU, ReSukiSU/BakaSU, MKSU, RKSU, SukiSU-Ultra, KoWSU, KernelSU-Next, and Wild KSU.
- **Baseband Guard (BBG):** LSM module providing protection against unauthorized userspace access to sensitive modem, NVRAM, and radio partitions.

### 2. Container & Userspace Support (DroidSpaces)
- **System V IPC:** POSIX message queues, semaphores, and shared memory (`CONFIG_SYSVIPC=y`).
- **KMI-Safe Struct Task Overlay:** IPC task state is placed inside `ANDROID_KABI_RESERVE` in `include/linux/sched.h`, avoiding any struct displacement.
- **Namespaces:** IPC namespaces (`CONFIG_IPC_NS=y`) and PID namespaces (`CONFIG_PID_NS=y`).
- **Virtual Networking:** MACVLAN support (`CONFIG_MACVLAN=y`).
- **devtmpfs:** Enabled without Android automount (`CONFIG_DEVTMPFS=y`).
- **Extended Attributes & ACLs:** tmpfs xattr and POSIX ACLs enabled.

### 3. Filesystems & Networking
- **NTFS3:** Built-in Paragon NTFS3 filesystem for fast USB drive read/write access.
- **IPv6 NAT & MASQUERADE:** Full IPv6 packet rewriting and masquerading.
- **nftables:** Full support for IPv4/IPv6/inet tables, connection tracking, NAT, limiters, and redirect/reject targets.
- **IPSet:** `hash:ip`, `hash:net`, and `xt_set` support.
- **TCP Congestion Control:** Cubic default; BBRv1 and CAKE queue discipline built-in.

### 4. Controller Feedback
- **Xbox:** Rumble and supported controller LEDs.
- **Nintendo:** Force feedback enabled.
- **Logitech:** Force feedback enabled across supported gamepad and steering wheel models.

For comprehensive architectural and configuration details, see [Documentation/features.md](Documentation/features.md).

---

## Installation

> [!WARNING]
> Use this image ONLY with the matching TB373FU firmware and vendor-module setup. The bootloader must already be unlocked. Always keep a tested backup of your stock `boot.img` before flashing.

### 1. Enter Fastbootd

Reboot the tablet into userspace fastboot (**fastbootd**):

```sh
adb reboot fastboot
```

Verify the target device and active slot:

```sh
fastboot devices
fastboot getvar product
fastboot getvar is-userspace
fastboot getvar current-slot
```

Ensure **`is-userspace: yes`** and verify your current slot (e.g. `a`). Ordinary bootloader-fastboot writes are unreliable on this platform; **always use fastbootd**.

### 2. Flash Boot Partition

Flash `boot.img` to the active slot:

```sh
fastboot flash boot_a boot.img
fastboot reboot
```

Do not flash `vendor_boot`, `dtbo`, `vbmeta`, or `*_dlkm` partitions.

### 3. Rollback Procedure

If the device fails to boot:
1. Re-enter fastbootd.
2. Restore your stock boot backup:
   ```sh
   fastboot flash boot_a stock_boot.img
   fastboot reboot
   ```

---

## Building from Source

Build the kernel using the optimized build and release script inside WSL:

```bash
make ARCH=arm64 LLVM=1 aphelion_defconfig && make -j$(nproc) ARCH=arm64 LLVM=1 Image
```

- Toolchain: Google AOSP Clang 17 (`/root/toolchains/clang-r487747c/bin`).
- Configuration: `arch/arm64/configs/aphelion_defconfig` (overlay: `arch/arm64/configs/aphelion_release.config`).
- Object caching: Intermediate `.o` files are preserved in `out/` for sub-15 second incremental rebuilds.

For detailed compilation instructions, see [Documentation/build.md](Documentation/build.md).

---

## Documentation Index

- [Architecture & Features](Documentation/features.md)
- [Build Guide & Toolchain](Documentation/build.md)
- [Flashing & Recovery](Documentation/flashing.md)
- [Release Notes & Keys](Documentation/releases/)
