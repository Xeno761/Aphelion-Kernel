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

## 2. Container & Userspace Support (DroidSpaces)

### Core Prerequisites
- **System V IPC (`CONFIG_SYSVIPC=y`):** Shared memory (`shm`), semaphores (`sem`), and message queues (`msg`).
- **KMI-Safe Struct Task Overlay:** Task-specific IPC state is mapped into `ANDROID_KABI_RESERVE(6, 7, 8)` inside `struct task_struct` (`include/linux/sched.h`), preventing any struct displacement and keeping stock MediaTek vendor modules 100% binary-compatible.
- **Namespaces:** IPC namespaces (`CONFIG_IPC_NS=y`) and PID namespaces (`CONFIG_PID_NS=y`).
- **Virtual Network Devices:** MACVLAN (`CONFIG_MACVLAN=y`) for isolated container networking.
- **devtmpfs:** Enabled (`CONFIG_DEVTMPFS=y`) without Android automount (`# CONFIG_DEVTMPFS_MOUNT is not set`).

---

## 3. Filesystems & Storage

- **NTFS3 (`CONFIG_NTFS3_FS=y`):** Native Paragon NTFS driver built-in for high-performance external USB NTFS storage.
- **tmpfs Extended Attributes & ACLs:** `CONFIG_TMPFS_XATTR=y` and `CONFIG_TMPFS_POSIX_ACL=y` enabled for POSIX-compliant userspace tools.
- **Retained Stock Filesystems:** EROFS, F2FS, Ext4, and exFAT remain enabled with standard OEM performance parameters.

---

## 4. Networking & Traffic Control

- **IPv6 NAT & Masquerade:** `CONFIG_IP6_NF_NAT=y` and `CONFIG_IP6_NF_TARGET_MASQUERADE=y`.
- **nftables Subsystem:** Full support for IPv4/IPv6/inet tables, connection tracking (`NFT_CT`), NAT (`NFT_NAT`, `NFT_MASQ`, `NFT_REDIR`), packet limiters, and rejection targets.
- **IPSet Support:** `CONFIG_IP_SET=y` with `hash:ip`, `hash:net`, and `xt_set` matchers.
- **TCP Congestion Control:**
  - Default: **CUBIC** (`CONFIG_DEFAULT_CUBIC=y`) remains the active default.
  - Option: **BBRv1** (`CONFIG_TCP_CONG_BBR=y`) built-in and selectable.
  - Queue Management: **CAKE** (`CONFIG_NET_SCH_CAKE=y`) available for advanced userspace bandwidth management.

---

## 5. Controller Feedback & Input

- **Xbox Gamepads:** Full rumble and LED status support via `CONFIG_JOYSTICK_XPAD_FF=y` and `CONFIG_JOYSTICK_XPAD_LEDS=y`.
- **Nintendo Controllers:** Force feedback enabled (`CONFIG_NINTENDO_FF=y`).
- **Logitech Gamepads:** Rumble and wheel feedback enabled (`CONFIG_LOGITECH_FF=y`, `CONFIG_LOGIRUMBLEPAD2_FF=y`, etc.).
- **PlayStation / Sony:** Stock DualShock / DualSense driver capabilities retained.
