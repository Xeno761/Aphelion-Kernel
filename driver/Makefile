# XenoOP: the module is embedded in a fixed 523864-byte vendor_boot slot,
# so build this driver for size. -Os wins over the default -O2 because
# ccflags-y is appended after KBUILD_CFLAGS.
ccflags-y += -Os -I$(src)/include
# Makefile for the Novatek NT36xxx touchscreen driver.
# add nt36xxx_platform.o for  penlink
ccflags-$(CONFIG_DRM_MEDIATEK_V2) += -I$(DEVICE_MODULES_PATH)/drivers/gpu/drm/mediatek/mediatek_v2/
obj-$(CONFIG_TOUCHSCREEN_NT36xxx_HOSTDL_SPI) += nt36532.o
nt36532-y += nt36xxx.o
nt36532-y += nt36xxx_fw_update.o
nt36532-y += nt36xxx_ext_proc.o
nt36532-y += nt36xxx_mp_ctrlram.o
nt36532-y += nt36xxx_platform.o
