# Aphelion Kernel Flashing & Bootloop Recovery Guide

## 1. Safety Checks Before Flashing

> [!WARNING]
> Always verify that your bootloader is unlocked and that you have a tested backup of your stock `boot.img` before flashing custom kernel images.

1. **Target Device:** Lenovo Idea Tab Pro (TB373FU / TB375FC - MediaTek MT6897 / MT8792 / Dimensity 8300).
2. **Flash Mode:** MUST be flashed in **fastbootd** (`is-userspace: yes`), never in legacy bootloader fastboot.
3. **Partition:** Flash only to the `boot` partition (`boot.img`). Do NOT flash as `vendor_boot` or `recovery`.

---

## 2. Standard Flashing Steps (Prebuilt `boot.img`)

1. Reboot the tablet into fastbootd:
   ```bash
   adb reboot fastboot
   ```
2. Verify userspace fastboot connection and active slot:
   ```bash
   fastboot devices
   fastboot getvar is-userspace
   fastboot getvar current-slot
   ```
   Confirm that `is-userspace` returns `yes` and check the active slot (`a` or `b`).

3. Flash the kernel `boot.img`:
   ```bash
   fastboot flash boot boot.img
   ```

4. Reboot to system:
   ```bash
   fastboot reboot
   ```

---

## 3. Bootloop Troubleshooting: Repack `Image` into Your Own `boot.img`

### Why Does a Bootloop Occur?
On Android 14 GKI devices, `boot.img` contains both the Linux kernel (`kernel`) and the generic first-stage `ramdisk`. If your tablet is running a different firmware version or custom ROM port (such as Lenovo ZUI 16 vs ZUI 17.5, or a Samsung One UI port / GSI):
* The ramdisk inside the generic `boot.img` may contain mismatched `fstab` mount points, AVB verity flags, or init scripts.
* Flashing a prebuilt `boot.img` across different OS versions can cause the tablet to loop at the Lenovo splash screen and fall back to recovery.

### The Fix: Keep Your Stock Ramdisk & Swap the Kernel `Image`
By injecting Aphelion's standalone `Image` into your **own firmware's stock `boot.img`**, you keep 100% of your ROM's native ramdisk, drivers, and init scripts while running Aphelion's high-performance kernel.

---

### Step-by-Step Repack Guide

#### Option A: On PC (Windows / Linux / WSL)

**Prerequisites:** Download `magiskboot` (extracted from the Magisk APK or Magisk repository) and Aphelion's standalone `Image`.

1. Place your ROM's stock `boot.img` and the Aphelion `Image` into an empty folder.
2. Unpack your stock `boot.img`:
   ```bash
   magiskboot unpack boot.img
   ```
   *(This creates `kernel`, `ramdisk.cpio`, and header metadata files).*
3. Replace the stock `kernel` with Aphelion's `Image`:
   * **Linux / WSL:**
     ```bash
     cp -f Image kernel
     ```
   * **Windows (PowerShell):**
     ```powershell
     Copy-Item -Path "Image" -Destination "kernel" -Force
     ```
4. Repack the boot image:
   ```bash
   magiskboot repack boot.img
   ```
   *(This generates `new-boot.img` containing your native stock ramdisk paired with the Aphelion kernel).*
5. Flash the repacked boot image in **fastbootd**:
   ```bash
   fastboot flash boot new-boot.img
   fastboot reboot
   ```

---

#### Option B: Directly on the Tablet (via Termux / Root Shell)

If you have root or access to a root shell:
1. Dump your current boot partition:
   ```bash
   su
   dd if=/dev/block/by-name/boot$(getprop ro.boot.slot_suffix) of=/sdcard/stock_boot.img
   ```
2. Navigate to a working directory in Termux:
   ```bash
   cd /data/local/tmp
   cp /sdcard/stock_boot.img ./boot.img
   cp /sdcard/Download/Image ./Image
   ```
3. Use Magisk's built-in `magiskboot` binary (`/data/adb/magisk/magiskboot`):
   ```bash
   /data/adb/magisk/magiskboot unpack boot.img
   cp -f Image kernel
   /data/adb/magisk/magiskboot repack boot.img
   ```
4. Flash the repacked image directly to your active boot slot:
   ```bash
   dd if=new-boot.img of=/dev/block/by-name/boot$(getprop ro.boot.slot_suffix) bs=4096 conv=fsync
   reboot
   ```

---

## 4. Emergency Rollback

If you ever need to revert:
1. Hold **Volume Down + Power** to re-enter fastboot mode.
2. Select **Fastbootd**.
3. Flash your original stock `boot.img`:
   ```bash
   fastboot flash boot stock_boot.img
   fastboot reboot
   ```
