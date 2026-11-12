# Aphelion Kernel v1.5.0_fixed — Major Update & Hotfix

**Target Platform:** Lenovo Idea Tab Pro (TB373FU / MediaTek Dimensity 8300 / MT6897)  
**Base:** Google Android Common Kernel (ACK) Linux 6.1.183 LTS (`android14-6.1-lts`)  
**Toolchain:** Google AOSP Official Pinned `clang-r487747c` (LLVM 17.0.2 + PGO + BOLT + LTO)  
**KMI Freeze:** 100% Bit-for-Bit Frozen (`struct task_struct`, `struct file`, `struct mm_struct`) — Complete binary compatibility with all 475 prebuilt stock vendor modules.

---

## Combined Changelog: v1.4.0 + v1.5.0

### 1. Touchscreen & Input Responsiveness (Light Tap Fix)
* **Eliminated Dropped Light Touches:** Neutralized artificial 1-bit binary pressure reporting on `NVTCapacitiveTouchScreen`. Android InputFlinger no longer filters out light or ultra-rapid finger contacts as 0-pressure noise.
* **100% Stylus & Palm Rejection Preservation:** Stylus channel (`touch-pen`) and active hardware palm rejection remain entirely intact and verified on the Lenovo Tab Pen Plus (BTP-131).
* **Eliminated Input Lag:** Input dispatch delay resolved to maintain immediate 144Hz input responsiveness across high-refresh UI and competitive games.

### 2. Next-Gen Memory Management (mTHP + ARM64 ContPTE)
* **Backported Multi-Size Transparent Huge Pages (mTHP):** Forward-ported from Linux 6.8+ into ACK 6.1 LTS.
* **ARM64 ContPTE (Contiguous Page Table Entries):** Hardware-level TLB amortization clustering 16 contiguous 4KB PTEs into a single 64KB ContPTE block, reducing memory access latency by up to 25%.
* **Anonymous Memory Acceleration:** 16KB, 32KB, and 64KB huge page allocations enabled with `inherit` policy for transparent app and game acceleration.
* **RANDOM_KMALLOC_CACHES:** Backported Linux 6.6 SLUB allocator hardening mitigating slab-based heap spraying exploits with zero measurable CPU penalty.

### 3. Scheduler & Interactive Cadence
* **BORE Scheduler (Burst-Oriented Response Enhancer):** Seamlessly injected into CFS using KABI reserve slots without altering core struct sizes. Automatically prioritizes bursty, interactive foreground UI threads while smoothly scheduling heavy background compute tasks.
* **144Hz RT Util Clamp Floor:** Hardened real-time task clamp floor (`sched_util_clamp_min_rt_default = 768`) to guarantee SurfaceFlinger and display compositor pipelines never drop frames during heavy workloads.
* **CPU Frequency Pegging Resolved:** Eliminated static uclamp frequency pinning, allowing Dimensity 8300 cores to dynamically scale and enter deep low-power sleep states (C-states).
* **TEO Cpuidle Governor:** Set Timer Events Oriented (TEO) idle governor as default with util-awareness.

### 4. Advanced Storage & Compression
* **Dual-Tier ZRAM Multi-Compression:** Built-in ZRAM with multi-algorithm pipelines:
  * **LZ4:** Primary low-latency compression stream for instant swap access.
  * **ZSTD:** Secondary high-ratio compression engine for long-term background app residency.
* **NTFS3 In-Kernel Support:** Full read/write Paragon NTFS3 filesystem support with LZX compression and POSIX ACLs enabled.

### 5. Gaming & Emulation (Windows / Proton / Winlator)
* **Native NTSync Primitive:** Backported `/dev/ntsync` kernel-level synchronization driver, providing near-native Windows NT synchronization object performance for Wine, Winlator, and Proton emulators.
* **Unprivileged Userspace Access:** Configured full non-root Android SELinux access to `/dev/ntsync`.

### 6. System Hygiene & Power Efficiency
* **MTK Wi-Fi Spam Suppression:** Suppressed recurring kernel log flood from `wlan_drv_gen4m_6897` (`halSetFWOwn`, `kalPerMonUpdate`, link metrics) that was previously consuming over 92% of printk bandwidth and causing CPU churn.
* **Debug Tax Elimination:** Stripped runtime UBSAN overhead, stack zeroing tax, and debug accounting overhead from release builds.
* **Security & Root Subsystem:** ReSukiSU/BakaSU v4.2.0-rc1 (`v35134`) with SUSFS v2.3.0 inline hooks + Baseband Guard (BBG) partition protection.

---

## Release Artifacts & Checksums

| File | SHA-256 Checksum | Description |
| :--- | :--- | :--- |
| **`boot.img`** | `cc203d09aebc55ea68bfb6415ad29cd13a981d7c9f660ccaf145d6b704b0756e` | Flashable AVB-signed boot image (67,108,864 bytes) |
| **`Image`** | `f348a165b8e30b44fc90e636de00fc175ffab3180a416832f960e00115be4625` | Raw uncompressed ARM64 kernel Image (36,571,648 bytes) |

---

## Flashing Instructions

### Method 1: Via Fastboot (PC / ADB)
```bash
fastboot flash boot boot.img
fastboot reboot
```

### Method 2: Via Root / Termux / Recovery
```bash
dd if=/sdcard/boot.img of=/dev/block/by-name/boot_a
dd if=/sdcard/boot.img of=/dev/block/by-name/boot_b
reboot
```

---

## How to Repack `Image` into Any Custom / Stock ROM `boot.img`

If you are running a different ROM version, custom firmware, or regional variant, you can easily repack the standalone `Image` into your own ROMs `boot.img` using either of the following methods:

### Option A: Using `magiskboot` (On Device / Termux / Linux)
`magiskboot` comes built into Magisk / KernelSU and preserves original header offsets and AVB hashes automatically:

```bash
# 1. Place your ROMs stock boot.img and the Aphelion Image in a working directory:
mkdir repack && cd repack
cp /path/to/stock/boot.img .
cp /path/to/Image .

# 2. Unpack the stock boot image:
magiskboot unpack boot.img

# 3. Replace the extracted kernel with Aphelion Image:
cp -f Image kernel

# 4. Repack the boot image:
magiskboot repack boot.img new-boot.img

# 5. Flash new-boot.img via fastboot:
fastboot flash boot new-boot.img
```

### Option B: Using Android Image Kitchen (AIK) on Windows / Linux
1. Download **Android Image Kitchen (AIK)**.
2. Drag and drop your ROMs `boot.img` onto `unpackimg.bat` (or `./unpackimg.sh` on Linux).
3. In the resulting `split_img/` folder, delete `boot.img-kernel` (or `boot.img-zImage`).
4. Copy the downloaded Aphelion `Image` into `split_img/` and rename it to `boot.img-kernel`.
5. Run `repackimg.bat` (or `./repackimg.sh`).
6. Flash the newly generated `image-new.img` via Fastboot:
   ```cmd
   fastboot flash boot image-new.img
   ```