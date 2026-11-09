# Aphelion Kernel Build Guide

## 1. Prerequisites & Environment

- **Host OS:** Windows with WSL 2 (Ubuntu 22.04+).
- **Filesystem Rule:** All kernel sources and compilation output directories MUST reside strictly on native WSL ext4 (`/root/Aphelion-Kernel` and `/root/Aphelion-Kernel-out`). Never compile across `/mnt/c/`.
- **Toolchain:** Google AOSP Clang 17 (`clang-r487747c` / LLVM 17.0.2 with PGO+BOLT).

## 2. Compilation Commands

Run the automated build and release synchronization script:

```bash
# In WSL:
./scripts/build_and_release.sh
```

Or manually:

```bash
export ARCH=arm64
export SUBARCH=arm64
export PATH="/root/toolchains/clang-r487747c/bin:$PATH"
export KBUILD_BUILD_TIMESTAMP=''
export KBUILD_BUILD_USER='builder'
export KBUILD_BUILD_HOST='wsl'

cd /root/Aphelion-Kernel
make ARCH=arm64 LLVM=1 O=/root/Aphelion-Kernel-out aphelion_defconfig
make -j$(nproc) ARCH=arm64 LLVM=1 O=/root/Aphelion-Kernel-out CC="ccache clang" Image
```

## 3. Incremental Acceleration

- **Kbuild `.o` Preservation:** Intermediate `.o` and `.cmd` object files are permanently preserved in `/root/Aphelion-Kernel-out`. For minor code changes or defconfig tweaks, incremental builds complete in **5 to 15 seconds**.
- **ccache:** Secondary cache layer configured at 40 GB (`~/.ccache`) with compression and neutralized timestamps.
