# Aphelion Kernel Features & Custom Modifications

A comprehensive catalog of modifications, security hardening, container prerequisites, and driver additions implemented in Aphelion Kernel.

---

## 1. Root Solution & Tamper Resistance

### ReSukiSU / BakaSU v4.2.0-rc1
- **Engine:** Integrated `v35134` (UAPI 4) with multi-manager certificate recognition.
- **SUSFS v2.3.0 Integration:** Built-in kernel-level inline hooks for hiding mount namespaces, process paths, open redirects, and kernel status (`sus_mount`, `sus_path`, `sus_kstat`, `sus_map`).
- **Multi-Manager Support:** Recognizes certificates for:
  - Official KernelSU
  - ReSukiSU / BakaSU
  - Magic-KSU / MKSU
  - RKSU
  - SukiSU-Ultra
  - KoWSU
  - KernelSU-Next `v3.4.0` (pinned hash: `79e590113c4c4c0c222978e413a5faa801666957b1212a328e46c00c69821bf7`)
  - Wild KSU `v3.1.2` (pinned hash: `52d52c546f75448464566da175d72b2c147bc5cb55a10886941da2a20ca2efac`)

### Baseband Guard (BBG) LSM
- Embedded security module in `CONFIG_LSM` (`baseband_guard`).
- Restricts direct userspace read/write access to sensitive modem, NVRAM, and radio partitions to protect device baseband integrity.

---

## 2. Scheduling, UI Responsiveness & 144Hz Latency Optimization

### BORE (Burst-Oriented Response Enhancer) Scheduler v5.4.4
- Integrated into Android Common Kernel 6.1 LTS via KABI-reserved fields (`ANDROID_KABI_RESERVE` in `sched_entity` and `task_struct`).
- Dynamically calculates task burstiness and prioritizes interactive UI/compositor threads over compute-intensive batch background tasks.
- Eliminates touch jitter, swipe lag, and UI stutters under heavy multitasking.

### 144Hz Real-Time Utilization Clamp (`sched_util_clamp_min_rt_default=768`)
- Android SurfaceFlinger and display rendering threads run as Real-Time (`SCHED_FIFO`/`SCHED_RR`).
- Default upstream and OEM configuration sets the RT clamp minimum to 0, permitting frequency drops during 144Hz refresh windows (6.94ms per frame).
- Hard-coded default floor set to 768/1024 (~75% CPU frequency floor) and protected against OEM userspace zeroing.
- Live hardware telemetry confirms **0.09%** frame jank rate with **5ms** frame latency.

### PELT 4x Frequency Ramp-Up Multiplier
- Configured `/proc/sys/kernel/sched_pelt_multiplier = 4`, reducing PELT half-life from 32ms to 8ms.
- Allows the CPU frequency governor to scale to maximum performance frequencies 4x faster upon touch input.

### TEO (Timer Events Oriented) Cpuidle Governor with Util-Awareness
- Configured as default idle governor with backported Arm utilization awareness (`9ce0f7c4bc`).
- Prevents CPU cores from dropping into 4.4ms deep-sleep C-states when touch interaction or frame rendering is imminent.

---

## 3. Memory Subsystem Modernization & Compression

### Built-in Monolithic ZRAM & zsmalloc
- Converted `CONFIG_ZRAM` and `CONFIG_ZSMALLOC` from loadable kernel modules into built-in monolithic drivers in `vmlinux`.
- Ensures instantaneous swap availability at early boot without module loader overhead.

### Dual-Tier Multi-Stream Recompression (LZ4 + ZSTD)
- Backported upstream 11-patch series (Sergey Senozhatsky & Alexey Romanov).
- **Tier 1 (Fast Compression):** Real-time write stream defaults to **LZ4** for instantaneous compression with zero UI delay.
- **Tier 2 (High-Density Recompression):** Cold idle memory is compacted into **ZSTD**, freeing up to 40% additional physical RAM.
- **Dynamic Sysfs Control:** Fully exposes `recomp_algorithm` and `recompress` sysfs interfaces for runtime memory recompression.

### In-Kernel Transparent Huge Pages (THP) Enforcer
- Intercepts userspace writes of `"never"` to `/sys/kernel/mm/transparent_hugepage/enabled` and locks policy to `madvise`.
- Guarantees 2MB huge-page allocation for memory-intensive applications and emulators.

---

## 4. Kernel Security & Exploit Mitigation

### 16-Way SLAB Heap Randomization (`CONFIG_RANDOM_KMALLOC_CACHES=y`)
- Backported from Linux 6.6 (Gong Ruiqi, Xiu Jianfeng, Kees Cook).
- Mitigates Use-After-Free (UAF) and heap-spraying exploits by creating 16 randomized slab caches per size class.
- Cache selection is dynamically calculated using a cryptographic hash: `caller ^ random_kmalloc_seed`.
- Strict KMI preservation ensures 100% binary compatibility with precompiled stock vendor modules.

---

## 5. PC Gaming & Windows NT Emulation (NTSYNC)

### Upstream Linux 6.14 NTSYNC Driver
- Dedicated synchronization driver (`/dev/ntsync`) backported for Wine, Proton, Winlator, and Mobox.
- Replaces high-overhead userspace `wineserver` IPC synchronization for Windows NT primitives (`WaitForMultipleObjects`, mutexes, semaphores, events) with kernel-space mutexes.
- Improves frame pacing and delivers substantial FPS gains in emulated Windows games on ARM64.
- World-accessible permissions (`0666`) and SELinux integration for containerized and non-root userspace.

---

## 6. Container & Userspace Support (DroidSpaces)

### Core Prerequisites
- **System V IPC (`CONFIG_SYSVIPC=y`):** Shared memory (`shm`), semaphores (`sem`), and message queues (`msg`).
- **KMI-Safe Struct Task Overlay:** Task-specific IPC state is mapped into `ANDROID_KABI_RESERVE` inside `struct task_struct`, preventing any struct displacement.
- **Namespaces:** IPC namespaces (`CONFIG_IPC_NS=y`), PID namespaces (`CONFIG_PID_NS=y`), and User namespaces (`CONFIG_USER_NS=y`).
- **Container Cgroups:** `CONFIG_CGROUP_DEVICE=y` and `CONFIG_CGROUP_PIDS=y`.
- **Virtual Network Devices:** MACVLAN (`CONFIG_MACVLAN=y`) and veth (`CONFIG_VETH=y`) for isolated container networking.
- **devtmpfs:** Enabled (`CONFIG_DEVTMPFS=y`) without Android automount.

---

## 7. Filesystems & Storage

- **NTFS3 with LZX & Xpress (`CONFIG_NTFS3_FS=y`):** Native Paragon NTFS driver with `CONFIG_NTFS3_LZX_XPRESS=y` and POSIX ACLs. Supports compressed Windows filesystems and full read/write speeds over USB 3.0.
- **tmpfs Extended Attributes & ACLs:** `CONFIG_TMPFS_XATTR=y` and `CONFIG_TMPFS_POSIX_ACL=y` enabled for POSIX-compliant userspace tools.
- **Retained Stock Filesystems:** EROFS, F2FS, Ext4, and exFAT remain enabled with standard OEM performance parameters.

---

## 8. Networking & Traffic Control

- **IPv6 NAT & Masquerade:** `CONFIG_IP6_NF_NAT=y` and `CONFIG_IP6_NF_TARGET_MASQUERADE=y`.
- **nftables Subsystem:** Full support for IPv4/IPv6/inet tables, connection tracking (`NFT_CT`), NAT (`NFT_NAT`, `NFT_MASQ`, `NFT_REDIR`), packet limiters, and rejection targets.
- **Docker NAT & Matchers:** `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y`, `CONFIG_NETFILTER_XT_TARGET_LOG=y`, `CONFIG_NETFILTER_XT_MATCH_RECENT=y`.
- **IPSet Support:** `CONFIG_IP_SET=y` with `hash:ip`, `hash:net`, and `xt_set` matchers.
- **TCP Congestion Control:**
  - Default: **CUBIC** (`CONFIG_DEFAULT_CUBIC=y`).
  - Option: **BBRv1** (`CONFIG_TCP_CONG_BBR=y`) built-in and selectable.
  - Queue Management: **CAKE** (`CONFIG_NET_SCH_CAKE=y`).

---

## 9. Controller Feedback & Input

- **Xbox Gamepads:** Full rumble and LED status support via `CONFIG_JOYSTICK_XPAD_FF=y` and `CONFIG_JOYSTICK_XPAD_LEDS=y`.
- **Nintendo Controllers:** Force feedback enabled (`CONFIG_NINTENDO_FF=y`).
- **Logitech Gamepads:** Rumble and wheel feedback enabled (`CONFIG_LOGITECH_FF=y`, `CONFIG_LOGIRUMBLEPAD2_FF=y`, etc.).
- **PlayStation / Sony:** Stock DualShock / DualSense driver capabilities retained.

---

## 10. Latency Optimization & Debug Tax Elimination

- **Stripped Debug Overheads:** `CONFIG_UBSAN`, `UBSAN_TRAP`, `UBSAN_BOUNDS`, `PER_VMA_LOCK_STATS`, `PAGE_OWNER`, `DEBUG_MEMORY_INIT`, `KUNIT`.
- **Allocation Efficiency:** Disabled `INIT_ON_ALLOC` memory zero-sweeping.
- **Optimized Kernel Command-Line Parameters:**
  - `workqueue.power_efficient=1`
  - `kfence.sample_interval=0`
  - `rcutree.enable_rcu_lazy=1`
  - `panic_on_oops=0`
  - `panic=5`
