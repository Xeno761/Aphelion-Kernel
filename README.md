# Aphelion Kernel For Lenovo TB373FU

This source contains the configuration and final kernel changes used for the
Aphelion 1.1 build with NTFS3 and controller feedback support. It is based on a
preserved local MT6897 6.1.138 working-source import, not a verified pristine
Motorola product release. The local baseline is
`b03d256b3cd1d35499c15956e72028e89c2c084f` (tree
`98f8eb82040aa07d1e74b8cdbfaec0c958ecb0a4`).

Selected stable updates through the local 6.1.148 integration and thirteen later
backports are retained with their original source references and attribution in
the release commit. Vendor adaptations and exclusions mean this is not an
unmodified complete upstream 6.1.148 or 6.1.182 tree. The existing 182 build label
is an inherited release identity, not a claim of complete 182 patch coverage.

## Release Configuration

- `arch/arm64/configs/aphelion_defconfig` is the complete generated configuration
  of the supplied NTFS3/controller-feedback build.
- `arch/arm64/configs/aphelion_release.config` records the release capability
  overlay. Old developer/iteration overlays have been removed.
- Existing IPC, namespace, tmpfs ACL/xattr, IPv6 NAT, nftables/IPSet, BBRv1 and
  optional CAKE capabilities are retained. Cubic remains the default TCP policy.
- NTFS3 and Xbox/Nintendo/Logitech feedback options are included; existing
  PlayStation/Sony support and OEM network/storage defaults are retained.
- BBRv3, CASS, ThinLTO, new root engines/SUSFS, Baseband-Guard, MemKernel, NetHunter
  additions and other abandoned development work are not part of this release.

The supplied image was built and packaged, but runtime boot/stability testing was
not performed. A release name without `rc` does not establish stability. Existing
vendor-module compatibility limitations and version-check policy are inherited;
this source does not claim a newly validated or security-hardened module ABI.

## Building

Use the Android clang-r487747c toolchain (Clang/LLD 17) and matching kernel build
tools. The build also requires the matching device-source tree providing the
external Kconfig/include dependencies. The preserved device-source identity is
`21677a12b263056d5459513868bff715d8bbcd4b`; it is not a verified pristine Motorola
release either. Keep it as a sibling named `kernel_device_modules-6.1`.

```sh
export PATH="$CLANG_DIR/bin:$KERNEL_BUILD_TOOLS/bin:$PATH"
make O=../out-aphelion ARCH=arm64 LLVM=1 \
    KCONFIG_EXT_PREFIX=../kernel_device_modules-6.1/ \
    DEVICE_MODULES_REL_DIR=../kernel_device_modules-6.1 aphelion_defconfig
make O=../out-aphelion ARCH=arm64 LLVM=1 \
    KCONFIG_EXT_PREFIX=../kernel_device_modules-6.1/ \
    DEVICE_MODULES_REL_DIR=../kernel_device_modules-6.1 -j6 Image
```

No boot images, signing keys, proprietary module binaries, device logs, internal
planning files or development caches are included. Existing kernel licensing,
copyright notices and upstream contribution guidance below are preserved.

# How do I submit patches to Android Common Kernels

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
