## Release Build

Aphelion 1.2.0 for **Lenovo Idea Tab Pro TB373FU / MT6897**.

| Item | Details |
| --- | --- |
| Kernel label | `6.1.182-aphelion-v1.2.0` |
| Source | Local 6.1.138 baseline, selected stable updates through 6.1.148, and 13 later backports |
| Asset | `boot.img` only, 64 MiB |

### Added Over Stock

- ReSukiSU/BakaSU v4.2.0-rc1 (`v35134`, UAPI 4) with SUSFS 2.3.0 inline hooks.
- Multi-manager certificate recognition for ReSukiSU/BakaSU, Official KernelSU, Magic-KSU/MKSU, RKSU, SukiSU-Ultra, KoWSU, KernelSU-Next v3.4.0, and Wild KSU v3.1.2.
- KernelSU-Next v3.4.0 is the verified full foreign core-manager match. Wild KSU v3.1.2 supports core operations but not profile editing. Current UAPI 6 managers and fork-only features are not compatible.
- Baseband-Guard LSM protection for critical partitions and device nodes.
- DroidSpaces kernel prerequisites: System V IPC, POSIX message queues, IPC/PID namespaces, devtmpfs without Android automount, and MACVLAN.
- tmpfs extended attributes and POSIX ACLs.
- IPv6 NAT/MASQUERADE, nftables, IPSet `hash:ip`/`hash:net`, and `xt_set`.
- Optional BBRv1 and built-in CAKE; **Cubic remains the default**, and CAKE is not applied automatically.
- NTFS3 filesystem support.
- Xbox LEDs/rumble, Nintendo rumble, and Logitech force feedback for the already-enabled drivers.
- Selected filesystem, crypto, key-state, bounds, and hardirq-accounting fixes.

Existing PlayStation/Sony feedback, MGLRU, PSI, zram/LZ4, USB Ethernet, and exFAT support are retained, not claimed as new additions. The 182 label does not claim complete upstream 6.1.182 coverage.

### Installation

Use only on the matching TB373FU firmware/vendor setup, with an **already unlocked bootloader** and your exact previously working boot image available for rollback. Download `boot.img` and verify its SHA-256:

```text
deb3919ddf2eb9f162d5680a739455b6b677d39f78b9e084d1b49755c4a55792
```

Enter fastbootd and verify the device, userspace mode, and active slot:

```sh
adb reboot fastboot
fastboot devices
fastboot getvar product
fastboot getvar is-userspace
fastboot getvar current-slot
```

Continue only when the correct tablet is connected, `is-userspace: yes`, and `current-slot: a`. Stop on any mismatch. Ordinary bootloader-fastboot writes were unreliable on this unit; use fastbootd.

```sh
fastboot flash boot_a boot.img
fastboot reboot
```

Proceed only after a successful write. Do not flash another slot, vendor_boot, DTBO, vbmeta, or DLKM partitions, erase data, or disable verification. No recovery/ZIP flashing is supported.

For rollback, return to fastbootd, recheck the same target/slot, then use your firmware-specific backup:

```sh
fastboot flash boot_a backup-boot.img
fastboot reboot
```

### Validation

The image was built successfully with Clang/LLD 17, repacked as an Android boot-header-v4 image, and verified with its matching SHA256_RSA2048 AVB footer. The packaged kernel payload matches the validated `6.1.182-aphelion-v1.2.0` build exactly. Extended runtime and stability testing has not been completed. Existing vendor-module compatibility limitations are inherited; this release is not a new complete ABI validation or a guarantee of stability.

Source and original patch credits are in the separate, feature-grouped [commit history](https://github.com/Xeno761/Aphelion-Kernel/commits/aphelion-public). Full installation details are in the [README](https://github.com/Xeno761/Aphelion-Kernel#installation).
