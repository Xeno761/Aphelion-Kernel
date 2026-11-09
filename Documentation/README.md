# Aphelion Kernel Documentation

This directory contains technical documentation, feature specifications, build instructions, and release notes for **Aphelion Kernel** on the **Lenovo Idea Tab Pro (TB373FU / MT6897 / Dimensity 8300)**.

## Index

1. [Features & Capabilities](features.md) - Complete technical breakdown of custom features, root integration, security enhancements, and subsystem patches.
2. [Compilation & Build Guide](build.md) - Instructions for compiling the kernel cleanly using Google AOSP Clang 17, Kbuild incremental optimization, and ccache.
3. [Flashing & Verification](flashing.md) - Step-by-step procedures for flashing `boot.img` via fastbootd, slot verification, and recovery safeguards.
4. [Releases & Changelogs](releases/) - Shipped version notes and signing artifacts.

## System Architecture

- **Target Device:** Lenovo Idea Tab Pro (TB373FU)
- **SoC:** MediaTek MT6897 (Dimensity 8300)
- **Base Kernel:** Google Android Common Kernel (ACK) `android14-6.1-lts` 
- **Architecture:** ARM64 (`aarch64`)
- **KMI Compliance:** Strict adherence to Android 14 GKI Kernel Module Interface (KMI). Core exported structs in `include/linux/` remain unmodified; custom state overlays use approved `ANDROID_KABI_RESERVE` fields to guarantee full compatibility with stock OEM/vendor prebuilt modules (`.ko`).
- **Toolchain:** Google AOSP Clang 17 (`clang-r487747c` / LLVM 17.0.2 with PGO+BOLT) with `LLVM=1`.
