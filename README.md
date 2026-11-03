<div align="center">

# Aphelion Kernel

### Lenovo Idea Tab Pro | TB373FU | MT6897

[![Release](https://img.shields.io/github/v/release/Xeno761/Aphelion-Kernel?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/releases/latest)
[![Source](https://img.shields.io/badge/Source-aphelion--public-blue?style=flat-square)](https://github.com/Xeno761/Aphelion-Kernel/tree/aphelion-public)
[![License](https://img.shields.io/badge/License-GPL--2.0-green?style=flat-square)](COPYING)

[Download](https://github.com/Xeno761/Aphelion-Kernel/releases/latest) | [Installation](#installation) | [Touch Driver](https://github.com/Xeno761/Aphelion-Kernel/tree/tb373fu-nt36532) | [Changelog](https://github.com/Xeno761/Aphelion-Kernel/commits/aphelion-public)

</div>

## Release Build

| Component | Details |
| --- | --- |
| Device | Lenovo TB373FU / MT6897 |
| Aphelion | 1.1.0 |
| Kernel build label | 6.1.182-aphelion-v1.1.0 |
| Source | Local 6.1.138 working baseline, selected stable updates through 6.1.148, and 13 later backports |
| Download | `boot.img` only |

The 182 version label does not mean that the complete upstream 6.1.182 series was
merged. This source uses vendor adaptations and selected fixes; the local 138
baseline is not claimed to be a verified pristine Motorola product release.

## Added Over Stock

### Container And Filesystem Support

- **DroidSpaces kernel prerequisites:** System V IPC, IPC namespaces, POSIX message
  queues, and PID namespaces, with the shipped KABI reserve adaptations.
- **devtmpfs** without Android automount, and **MACVLAN** support.
- **tmpfs extended attributes and POSIX ACLs**.
- **NTFS3** built in for NTFS USB-drive filesystem support.

These are kernel capabilities, not a guarantee that every container, mount, or
userspace application works without its own setup.

### Networking

- **IPv6 NAT and MASQUERADE**.
- **nftables** with IPv4/IPv6/inet tables and the shipped NAT, connection-tracking,
  limit, reject, redirect, and compatibility support.
- **IPSet** `hash:ip`, `hash:net`, and `xt_set` support.
- **BBRv1** available as a TCP congestion-control option.
- **CAKE** available as a built-in queue-management option.

**Cubic remains the default.** CAKE is not applied automatically; traffic shaping
requires suitable userspace configuration and bandwidth settings.

### Controller Feedback

- **Xbox:** rumble and supported controller LEDs.
- **Nintendo:** rumble support.
- **Logitech:** force feedback for the enabled controller families.

Existing PlayStation/Sony support is retained, not claimed as a new addition.
The release also retains its existing MGLRU, PSI, zram/LZ4, USB Ethernet, and exFAT
capabilities without presenting them as newly implemented performance features.

### Fixes

Selected stable updates and 13 additional fixes cover ext4, buffer lifetime,
crypto validation, key-state ordering, formatted-time pointer checks, IDR bounds,
and hardirq-safe flexible-proportion accounting. Feature-grouped commits preserve
their source references and original integration timeline.

## Optional Touch Driver

NT36532 touchscreen recovery fixes, driver source and separate packages are on the
[TB373FU touch-driver branch](https://github.com/Xeno761/Aphelion-Kernel/tree/tb373fu-nt36532).
Read its installation, AVB and rollback guide and check compatibility with your
kernel and firmware. The driver package has a separate vendor_boot procedure;
the kernel-only installation below remains a separate process.

## Installation

Use this image only with the matching TB373FU firmware/vendor-module setup. Keep a
known-good boot image and a tested way to return to fastbootd before flashing.
The bootloader must already be unlocked; unlocking can erase data and is not part
of these instructions. Do not use this image on another device or assume that
every firmware version is compatible.

### 1. Download And Verify

Download `boot.img` from [Release Build](https://github.com/Xeno761/Aphelion-Kernel/releases/latest)
and open a terminal in the same folder using recent Android platform-tools.

```powershell
Get-FileHash .\boot.img -Algorithm SHA256
```

Expected SHA-256:

```text
7d15a84df04788dbc0bad198340ab151e7766428f63c3cacd0e815545be5b728
```

### 2. Enter Fastbootd And Check The Target

```sh
adb reboot fastboot
fastboot devices
fastboot getvar product
fastboot getvar is-userspace
fastboot getvar current-slot
```

Wait for **`is-userspace: yes`** and verify that the target is your TB373FU and
**`current-slot: a`**. Stop if a check fails or the active slot is not `a`; do not
guess a partition or change slots. Ordinary bootloader-fastboot writes were
unreliable on this unit, so use **fastbootd**, not `adb reboot bootloader`.

### 3. Flash Only The Active Boot Partition

```sh
fastboot flash boot_a boot.img
fastboot reboot
```

Continue only if the write finishes successfully. Do not flash `boot_b`,
`vendor_boot`, `dtbo`, `vbmeta`, or a `*_dlkm` partition, erase data, or disable
verification. No recovery/ZIP installer is used.

### Rollback

If Android does not boot, use the device's recovery procedure to reach fastbootd,
recheck the same target/slot, and restore your exact previously working image:

```sh
fastboot flash boot_a backup-boot.img
fastboot reboot
```

Do not download a random image as a substitute for that firmware-specific backup.

## Validation

The supplied image was built and packaged successfully. Runtime boot and stability
testing of this final NTFS3/controller-feedback image was not performed. Its
release name does not establish stability or a new vendor-module ABI validation.

## Source And Credits

Release configuration: `arch/arm64/configs/aphelion_defconfig`; capability overlay:
`arch/arm64/configs/aphelion_release.config`. Building requires clang-r487747c
(Clang/LLD 17) and the matching `kernel_device_modules-6.1` Kconfig/include tree.

Kernel licensing, copyrights, and upstream author credits are retained. The
feature-grouped commit messages contain the original patch authors, upstream and
stable references, and vendor-adaptation notes. See [COPYING](COPYING),
[CREDITS](CREDITS), and the [source history](https://github.com/Xeno761/Aphelion-Kernel/commits/aphelion-public).

<details>
<summary>Upstream Android Common contribution guidance</summary>

## How do I submit patches to Android Common Kernels

1. BEST: Make all of your changes to upstream Linux. If appropriate, backport to the stable releases.
   These patches will be merged automatically in the corresponding common kernels. If the patch is already
   in upstream Linux, post a backport of the patch that conforms to the patch requirements below.
   - Do not send patches upstream that contain only symbol exports. To be considered for upstream Linux,
additions of `EXPORT_SYMBOL_GPL()` require an in-tree modular driver that uses the symbol -- so include
the new driver or changes to an existing driver in the same patchset as the export.
   - When sending patches upstream, the commit message must contain a clear case for why the patch
is needed and beneficial to the community. Enabling out-of-tree drivers or functionality is not
not a persuasive case.

2. LESS GOOD: Develop your patches out-of-tree (from an upstream Linux point-of-view). Unless these are
   fixing an Android-specific bug, these are very unlikely to be accepted unless they have been
   coordinated with kernel-team@android.com. If you want to proceed, post a patch that conforms to the
   patch requirements below.

# Common Kernel patch requirements

- All patches must conform to the Linux kernel coding standards and pass `scripts/checkpatch.pl`
- Patches shall not break gki_defconfig or allmodconfig builds for arm, arm64, x86, x86_64 architectures
(see  https://source.android.com/setup/build/building-kernels)
- If the patch is not merged from an upstream branch, the subject must be tagged with the type of patch:
`UPSTREAM:`, `BACKPORT:`, `FROMGIT:`, `FROMLIST:`, or `ANDROID:`.
- All patches must have a `Change-Id:` tag (see https://gerrit-review.googlesource.com/Documentation/user-changeid.html)
- If an Android bug has been assigned, there must be a `Bug:` tag.
- All patches must have a `Signed-off-by:` tag by the author and the submitter

Additional requirements are listed below based on patch type

## Requirements for backports from mainline Linux: `UPSTREAM:`, `BACKPORT:`

- If the patch is a cherry-pick from Linux mainline with no changes at all
    - tag the patch subject with `UPSTREAM:`.
    - add upstream commit information with a `(cherry picked from commit ...)` line
    - Example:
        - if the upstream commit message is
```
        important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>
```
>- then Joe Smith would upload the patch for the common kernel as
```
        UPSTREAM: important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>

        Bug: 135791357
        Change-Id: I4caaaa566ea080fa148c5e768bb1a0b6f7201c01
        (cherry picked from commit c31e73121f4c1ec41143423ac6ce3ce6dafdcec1)
        Signed-off-by: Joe Smith <joe.smith@foo.org>
```

- If the patch requires any changes from the upstream version, tag the patch with `BACKPORT:`
instead of `UPSTREAM:`.
    - use the same tags as `UPSTREAM:`
    - add comments about the changes under the `(cherry picked from commit ...)` line
    - Example:
```
        BACKPORT: important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>

        Bug: 135791357
        Change-Id: I4caaaa566ea080fa148c5e768bb1a0b6f7201c01
        (cherry picked from commit c31e73121f4c1ec41143423ac6ce3ce6dafdcec1)
        [joe: Resolved minor conflict in drivers/foo/bar.c ]
        Signed-off-by: Joe Smith <joe.smith@foo.org>
```

## Requirements for other backports: `FROMGIT:`, `FROMLIST:`,

- If the patch has been merged into an upstream maintainer tree, but has not yet
been merged into Linux mainline
    - tag the patch subject with `FROMGIT:`
    - add info on where the patch came from as `(cherry picked from commit <sha1> <repo> <branch>)`. This
must be a stable maintainer branch (not rebased, so don't use `linux-next` for example).
    - if changes were required, use `BACKPORT: FROMGIT:`
    - Example:
        - if the commit message in the maintainer tree is
```
        important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>
```
>- then Joe Smith would upload the patch for the common kernel as
```
        FROMGIT: important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>

        Bug: 135791357
        (cherry picked from commit 878a2fd9de10b03d11d2f622250285c7e63deace
         https://git.kernel.org/pub/scm/linux/kernel/git/foo/bar.git test-branch)
        Change-Id: I4caaaa566ea080fa148c5e768bb1a0b6f7201c01
        Signed-off-by: Joe Smith <joe.smith@foo.org>
```


- If the patch has been submitted to LKML, but not accepted into any maintainer tree
    - tag the patch subject with `FROMLIST:`
    - add a `Link:` tag with a link to the submittal on lore.kernel.org
    - add a `Bug:` tag with the Android bug (required for patches not accepted into
a maintainer tree)
    - if changes were required, use `BACKPORT: FROMLIST:`
    - Example:
```
        FROMLIST: important patch from upstream

        This is the detailed description of the important patch

        Signed-off-by: Fred Jones <fred.jones@foo.org>

        Bug: 135791357
        Link: https://lore.kernel.org/lkml/20190619171517.GA17557@someone.com/
        Change-Id: I4caaaa566ea080fa148c5e768bb1a0b6f7201c01
        Signed-off-by: Joe Smith <joe.smith@foo.org>
```

## Requirements for Android-specific patches: `ANDROID:`

- If the patch is fixing a bug to Android-specific code
    - tag the patch subject with `ANDROID:`
    - add a `Fixes:` tag that cites the patch with the bug
    - Example:
```
        ANDROID: fix android-specific bug in foobar.c

        This is the detailed description of the important fix

        Fixes: 1234abcd2468 ("foobar: add cool feature")
        Change-Id: I4caaaa566ea080fa148c5e768bb1a0b6f7201c01
        Signed-off-by: Joe Smith <joe.smith@foo.org>
```

- If the patch is a new feature
    - tag the patch subject with `ANDROID:`
    - add a `Bug:` tag with the Android bug (required for android-specific features)

</details>
