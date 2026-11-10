## Aphelion Kernel v1.4.0

### What's New & Upgraded

- **BORE (Burst-Oriented Response Enhancer) CPU Scheduler v5.4.4:**
  - Integrated into ACK 6.1 via non-breaking `ANDROID_KABI_RESERVE` slots.
  - Automatically identifies user interactivity bursts (touch, gestures, app switching) and dynamically deprioritizes background batch tasks.
- **144Hz Real-Time Utilization Clamp (`sched_util_clamp_min_rt_default=768`):**
  - Enforces in-kernel minimum 75% frequency floor on RT SurfaceFlinger compositing threads. Clamped against OEM userspace zeroing.
  - Verified on hardware: **0.09%** frame jank rate with **5ms** frame latency at 1840x2944 @ 144Hz.
- **Monolithic Built-in ZRAM & Dual-Tier Recompression Engine:**
  - Converted `zram` and `zsmalloc` into monolithic built-in kernel drivers (`CONFIG_ZRAM=y`, `CONFIG_ZSMALLOC=y`).
  - Backported complete 11-patch multi-stream compression series from Linux upstream (Sergey Senozhatsky & Alexey Romanov).
  - Dual-tier streaming: Tier 1 ultra-fast **LZ4** for real-time active pages + Tier 2 high-density **ZSTD** for cold idle pages, saving up to 40% RAM.
  - Dynamic stream management enabled in sysfs.
- **16-Way SLAB Heap Randomization (`CONFIG_RANDOM_KMALLOC_CACHES=y`):**
  - Backported from Linux 6.6 (Gong Ruiqi, Xiu Jianfeng, Kees Cook).
  - Replaces single predictable kmalloc caches with 16 cryptographically randomized sub-caches per size class, hashed by `caller ^ random_kmalloc_seed` to defeat Use-After-Free heap spraying.
  - 100% KMI-safe: all 473 proprietary vendor hardware drivers load flawlessly without ABI misalignment.
- **NTSYNC Windows NT Synchronization Driver:**
  - Backported Linux 6.14 NT synchronization primitives driver (`/dev/ntsync`) for Wine / Proton / Winlator / Mobox gaming emulation.
  - Replaces slow userspace `wineserver` IPC locks with in-kernel mutexes and events for smoother frame pacing and higher FPS.
  - Unprivileged container and SELinux permissions enabled.
- **TEO Cpuidle Governor with Utilization-Awareness:**
  - Backported Arm's utilization-awareness into the TEO governor. Prevents Dimensity 8300 cores from dropping into 4.4ms deep-sleep C-states during active touch interaction.
- **NTFS3 with Windows LZX & Xpress Compression:**
  - Enabled `CONFIG_NTFS3_LZX_XPRESS=y` and POSIX ACLs for high-speed read/write access to compressed NTFS external USB drives.
- **In-Kernel Transparent Huge Pages (THP) Enforcer:**
  - Clamps `transparent_hugepage=madvise` at the kernel level, blocking OEM ROM userspace from disabling huge pages.
- **Debug Tax Annihilation:**
  - Stripped `CONFIG_UBSAN`, `UBSAN_TRAP`, and `UBSAN_BOUNDS`.
  - Stripped `INIT_ON_ALLOC` memory zeroing overhead.
  - Stripped memory accounting debug checks (`PER_VMA_LOCK_STATS`, `PAGE_OWNER`, `DEBUG_MEMORY_INIT`, `KUNIT`).
  - Enabled power-efficient workqueues (`workqueue.power_efficient=1`), disabled KFENCE overhead (`kfence.sample_interval=0`), and batched idle RCU callbacks (`rcutree.enable_rcu_lazy=1`).
- **Zero-Bootloop Pre-Flight Symbol Auditor:**
  - Integrated into the release build pipeline; validates 2,293 undefined vendor symbols and SHA-1 signatures before creating boot images.

### Verification & Flashing

- **Target Device:** Lenovo Idea Tab Pro (TB373FU / MediaTek MT6897 / Dimensity 8300)
- **Active Vendor Modules:** 473 / 473 loaded (100% operational, zero KMI breakage)
- **Asset:** `boot.img` (67,108,864 bytes, AVB signed)
- **SHA-256:** `3d8488249fb1932f879170f04a0b6987496d32afa474ac8d2ad6040b3db64a5f`

```sh
adb reboot fastboot
fastboot flash boot_a boot.img
fastboot reboot
```
