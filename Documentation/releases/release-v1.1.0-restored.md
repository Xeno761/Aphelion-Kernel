## Release Build

Aphelion 1.1.0 for **Lenovo Idea Tab Pro TB373FU / MT6897**.

| Item | Details |
| --- | --- |
| Kernel label | `6.1.182-aphelion-v1.1.0` |
| Source | Local 6.1.138 baseline, selected stable updates through 6.1.148, and 13 later backports |
| Asset | `boot.img` only, 64 MiB |

### Added Over Stock

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
7d15a84df04788dbc0bad198340ab151e7766428f63c3cacd0e815545be5b728
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

The supplied image was built and packaged successfully. Runtime boot and stability testing were not performed. Existing vendor-module compatibility limitations are inherited; this release is not a new complete ABI validation or a guarantee of stability.

Source and original patch credits are in the separate, feature-grouped [commit history](https://github.com/Xeno761/Aphelion-Kernel/commits/aphelion-public). Full installation details are in the [README](https://github.com/Xeno761/Aphelion-Kernel#installation).
