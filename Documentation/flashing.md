# Aphelion Kernel Flashing Guide

## 1. Safety Checks Before Flashing

> [!WARNING]
> Always verify that your bootloader is unlocked and that you have a tested backup of your stock `boot.img` or working recovery before flashing custom kernel images.

1. **Target Device:** Lenovo Idea Tab Pro TB373FU (MT6897 / Dimensity 8300).
2. **Flash Mode:** MUST be flashed in **fastbootd** (`is-userspace: yes`), never in bootloader fastboot.
3. **Partition:** Flash only to the `boot` partition (`boot.img`). Do NOT flash as `vendor_boot` or `recovery`.

## 2. Flashing Steps

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

## 3. Rollback Safeguard

If the tablet fails to boot or experiences a bootloop:
1. Hold Volume Down + Power to re-enter fastboot mode.
2. Select Fastbootd / Recovery.
3. Restore your stock `boot.img`:
   ```bash
   fastboot flash boot stock_boot.img
   fastboot reboot
   ```
