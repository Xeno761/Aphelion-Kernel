<div align="center">

# Aphelion Kernel

### Lenovo Idea Tab Pro | TB373FU | MT6897 (Dimensity 8300)

[![Release](https://img.shields.io/github/v/release/Xeno761/Aphelion-Kernel?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/releases/latest)
[![Source](https://img.shields.io/badge/Source-aphelion--public-blue?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/tree/aphelion-public)
[![License](https://img.shields.io/badge/License-GPL--2.0-green?style=flat-square)](COPYING)

[Download](https://github.com/Xeno761/Aphelion-Kernel/releases/latest) | [Installation](#installation) | [Documentation](Documentation/) | [Changelog](CHANGELOG.md)

</div>

## Overview

**Aphelion Kernel** is an ultra-optimized, high-performance, and KMI-compliant Android 14 GKI kernel customized specifically for the **Lenovo Idea Tab Pro (TB373FU)** powered by the MediaTek MT6897 (Dimensity 8300) SoC.

The kernel tree is aligned directly with Google's official Android Common Kernel (ACK) **`android14-6.1-lts`**, ensuring absolute compliance with Android's frozen Kernel Module Interface (KMI) and 100% binary ABI compatibility with stock MediaTek hardware drivers.

## Build Information

| Component | Details |
| --- | --- |
| Target Device | Lenovo Idea Tab Pro (TB373FU / MT6897 / Dimensity 8300) |
| Architecture | ARM64 (`aarch64`) |
| Base Tree | Google ACK `android14-6.1-lts` (Linux 6.1.183 LTS) |
| Toolchain | Google AOSP Clang 17 (`clang-r487747c` / LLVM 17.0.2) |
| Status | Verified on-device (TB373FU); all 473 vendor modules active |
| Active Display Mode | 1840 x 2944 @ 144.0 Hz |
| Shipped Asset | `boot.img` only (67,108,864 bytes, AVB signed) |

> [!NOTE]
> The source strictly preserves KMI boundary compatibility: core exported struct sizes in `include/linux/` remain unaltered. Task, scheduler, and namespace additions utilize Android KABI reserved fields (`ANDROID_KABI_RESERVE`).

---

## Added Over Stock

### 1. High-Refresh Responsiveness & 144Hz Latency Optimization
- **BORE (Burst-Oriented Response Enhancer) Scheduler v5.4.4:** Upstream CPU scheduler integration that prioritizes interactive UI threads and user gestures over background workloads. Swiping, app launches, and desktop animations feel exceptionally fluid.
- **144Hz Real-Time Utilization Clamp (`sched_util_clamp_min_rt_default=768`):** Enforces a minimum 75% CPU frequency floor on SurfaceFlinger and display rendering threads, clamped against OEM userspace resets. Drops frame jank rate to **0.09%** with a rock-solid **5ms** frame latency.
- **PELT 4x Frequency Ramp-Up Multiplier (`sched_pelt_multiplier = 4`):** Halves PELT accumulation window from 32ms to 8ms, scaling CPU frequencies to peak performance 4x faster upon touch input.
- **TEO Cpuidle Governor with Util-Awareness:** Prioritizes TEO governor with backported Arm utilization awareness, preventing CPU cores from entering deep sleep C-states during active touch interaction.

### 2. Memory Modernization & Dual-Tier ZRAM Recompression
- **Monolithic Built-in Drivers:** Converted `CONFIG_ZRAM=y` and `CONFIG_ZSMALLOC=y` into core kernel drivers, eliminating module loading latency at early boot.
- **Dual-Tier Multi-Stream Recompression (LZ4 + ZSTD):** Backported upstream 11-patch multi-stream series. Uses ultra-fast **LZ4** for real-time active memory compression and high-density **ZSTD** for cold idle background pages, saving up to 40% more physical RAM.
- **Dynamic Sysfs Stream Control:** Exposes runtime memory recompression triggers directly via `/sys/block/zram0/recompress`.
- **In-Kernel Transparent Huge Pages (THP) Enforcer:** Intercepts OEM ROM userspace `"never"` writes and locks THP policy to `madvise`, unlocking huge 2MB pages for emulators and databases.

### 3. Kernel Security & Exploit Mitigation
- **16-Way SLAB Heap Randomization (`CONFIG_RANDOM_KMALLOC_CACHES=y`):** Backported from Linux 6.6. Replaces predictable kmalloc caches with 16 cryptographically randomized sub-caches per size class, mathematically defeating Use-After-Free (UAF) and heap-spraying exploits without breaking vendor module KMI.
- **ReSukiSU / BakaSU:** Embedded with SUSFS inline hooks (`sus_path`, `sus_mount`, `sus_kstat`, `sus_map`).
- **Multi-Manager Certificate Recognition:** Native support for Official KernelSU, ReSukiSU/BakaSU, MKSU, RKSU, SukiSU-Ultra, KoWSU, KernelSU-Next, and Wild KSU.
- **Baseband Guard (BBG):** LSM module providing protection against unauthorized userspace access to sensitive modem, NVRAM, and radio partitions.

### 4. PC Gaming & Windows Emulation (NTSYNC)
- **Linux 6.14 NTSYNC Driver (`/dev/ntsync`):** Dedicated in-kernel Windows NT synchronization primitives driver. Replaces slow userspace `wineserver` IPC locks with kernel mutexes and events, significantly accelerating frame rates and frame pacing in Winlator, Mobox, Termux-Box, and Proton/Wine gaming.
- **Container & SELinux Ready:** Granted `0666` unprivileged permissions for rootless container access.

### 5. Container & Userspace Support (DroidSpaces)
- **System V IPC:** POSIX message queues, semaphores, and shared memory (`CONFIG_SYSVIPC=y`).
- **KMI-Safe Struct Task Overlay:** IPC task state is placed inside `ANDROID_KABI_RESERVE` in `include/linux/sched.h`.
- **Namespaces:** IPC namespaces (`CONFIG_IPC_NS=y`), PID namespaces (`CONFIG_PID_NS=y`), and User namespaces (`CONFIG_USER_NS=y`).
- **Container Cgroups & Devices:** `CONFIG_CGROUP_DEVICE=y` and `CONFIG_CGROUP_PIDS=y`.
- **Virtual Networking:** MACVLAN support (`CONFIG_MACVLAN=y`) and veth (`CONFIG_VETH=y`).
- **devtmpfs:** Enabled without Android automount (`CONFIG_DEVTMPFS=y`).

### 6. Filesystems & Storage
- **NTFS3 with LZX & Xpress (`CONFIG_NTFS3_FS=y`):** Native Paragon NTFS driver with `CONFIG_NTFS3_LZX_XPRESS=y` and POSIX ACLs. Fast, native read/write access to external USB hard drives and compressed Windows storage.
- **tmpfs Extended Attributes & ACLs:** `CONFIG_TMPFS_XATTR=y` and `CONFIG_TMPFS_POSIX_ACL=y` enabled.

### 7. Networking & Traffic Control
- **IPv6 NAT & MASQUERADE:** Full IPv6 packet rewriting and masquerading.
- **nftables:** Full support for IPv4/IPv6/inet tables, connection tracking, NAT, limiters, and redirect/reject targets.
- **Docker NAT Support:** `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y`, `CONFIG_NETFILTER_XT_TARGET_LOG=y`, `CONFIG_NETFILTER_XT_MATCH_RECENT=y`.
- **IPSet:** `hash:ip`, `hash:net`, and `xt_set` support.
- **TCP Congestion Control:** Cubic default; BBRv1 and CAKE queue discipline built-in.

### 8. Controller Feedback
- **Xbox:** Rumble and supported controller LEDs.
- **Nintendo:** Force feedback enabled.
- **Logitech:** Force feedback enabled across supported gamepad and steering wheel models.

### 9. Debloat & Zero Debug Tax
- **Stripped Debug Overheads:** Removed `CONFIG_UBSAN`, `UBSAN_TRAP`, `UBSAN_BOUNDS`, `PER_VMA_LOCK_STATS`, `PAGE_OWNER`, `DEBUG_MEMORY_INIT`, `KUNIT`.
- **Allocation Efficiency:** Disabled `INIT_ON_ALLOC` memory zero-sweeping.
- **Optimized Kernel Parameters:** `workqueue.power_efficient=1`, `kfence.sample_interval=0`, `rcutree.enable_rcu_lazy=1`, `panic_on_oops=0`, `panic=5`.

For comprehensive architectural details, see [Documentation/features.md](Documentation/features.md).

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
- [Changelog & Release History](CHANGELOG.md)
- [Build Guide & Toolchain](Documentation/build.md)
- [Flashing & Recovery](Documentation/flashing.md)
- [Release Notes & Keys](Documentation/releases/)
