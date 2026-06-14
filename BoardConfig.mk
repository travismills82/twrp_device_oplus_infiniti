#
# Copyright (C) 2025 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Building with minimal manifest
ALLOW_MISSING_DEPENDENCIES                      := true
BUILD_BROKEN_DUP_RULES                          := true
BUILD_BROKEN_ELF_PREBUILT_PRODUCT_COPY_FILES    := true

BUILD_BROKEN_NINJA_USES_ENV_VARS    += RTIC_MPGEN
BUILD_BROKEN_PLUGIN_VALIDATION      := soong-libaosprecovery_defaults soong-libguitwrp_defaults soong-vold_defaults

# Architecture
TARGET_ARCH := arm64
TARGET_ARCH_VARIANT := armv8-a
TARGET_CPU_ABI := arm64-v8a
TARGET_CPU_VARIANT := generic
TARGET_CPU_VARIANT_RUNTIME := oryon

# A/B
AB_OTA_PARTITIONS := \
    boot \
    init_boot \
    vendor_boot \
    dtbo \
    odm \
    product \
    system \
    system_ext \
    system_dlkm \
    vbmeta \
    vbmeta_system \
    vbmeta_vendor \
    vendor \
    vendor_dlkm

# AB partitions for oplus
AB_OTA_PARTITIONS += \
    my_bigball \
    my_carrier \
    my_company \
    my_engineering \
    my_heytap \
    my_manifest \
    my_preload \
    my_product \
    my_region \
    my_stock

# Battery
TW_CUSTOM_BATTERY_PATH := "/sys/class/power_supply/battery"
TW_BATTERY_SYSFS_WAIT_SECONDS := 6

# Bootloader
PRODUCT_PLATFORM                := canoe
TARGET_BOOTLOADER_BOARD_NAME    := canoe

# Crypto
BOARD_USES_METADATA_PARTITION   := true
TW_INCLUDE_CRYPTO               := true
TW_INCLUDE_CRYPTO_FBE           := true
TW_INCLUDE_OMAPI                := true
TW_OZIP_DECRYPT_KEY             := 0000

# Debug
TARGET_USES_LOGD                := true
TWRP_INCLUDE_LOGCAT             := true
TARGET_RECOVERY_DEVICE_MODULES  += debuggerd
TARGET_RECOVERY_DEVICE_MODULES  += strace
RECOVERY_BINARY_SOURCE_FILES    += $(TARGET_OUT_EXECUTABLES)/debuggerd
RECOVERY_BINARY_SOURCE_FILES    += $(TARGET_OUT_EXECUTABLES)/strace

# File systems
TARGET_USERIMAGES_USE_F2FS := true
TW_USE_DMCTL               := true
TARGET_USERIMAGES_USE_EROFS := true
BOARD_EROFS_PCLUSTER_SIZE := 262144
BOARD_EROFS_SHARE_DUP_BLOCKS := true

# Init
TARGET_INIT_VENDOR_LIB          := //$(DEVICE_PATH):libinit_oplus_infiniti
TARGET_RECOVERY_DEVICE_MODULES  += libinit_oplus_infiniti

# Kernel
TARGET_KERNEL_ARCH          := arm64
TARGET_KERNEL_HEADER_ARCH   := arm64
BOARD_KERNEL_IMAGE_NAME     := Image
BOARD_BOOT_HEADER_VERSION   := 4
BOARD_KERNEL_PAGESIZE       := 4096
BOARD_MKBOOTIMG_ARGS        += --header_version $(BOARD_BOOT_HEADER_VERSION)
BOARD_MKBOOTIMG_ARGS        += --pagesize $(BOARD_KERNEL_PAGESIZE)
#TARGET_PREBUILT_KERNEL      := device/oplus/infiniti/Image
BOARD_RAMDISK_USE_LZ4       := true

# Partitions
BOARD_PROPERTY_OVERRIDES_SPLIT_ENABLED  := true
BOARD_RECOVERYIMAGE_PARTITION_SIZE      := 0x6400000

BOARD_SUPER_PARTITION_SIZE                  := 18907922432
BOARD_SUPER_PARTITION_GROUPS                := qti_dynamic_partitions
BOARD_QTI_DYNAMIC_PARTITIONS_SIZE           := 18903728128
BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST := system system_ext product vendor vendor_dlkm odm
BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST += my_bigball my_carrier my_company my_engineering my_heytap my_manifest my_preload my_product my_region my_stock

BOARD_ODMIMAGE_FILE_SYSTEM_TYPE := ext4
TARGET_COPY_OUT_ODM             := odm
TARGET_COPY_OUT_VENDOR          := vendor

# Platform
TARGET_BOARD_PLATFORM := sm8850
TARGET_BOARD_PLATFORM_GPU := qcom-adreno840
QCOM_BOARD_PLATFORMS += sm8850

# Power
ENABLE_CPUSETS := true
ENABLE_SCHEDBOOST := true

# Recovery
BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE    := true
TARGET_RECOVERY_PIXEL_FORMAT                := RGBX_8888
TW_INCLUDE_FASTBOOTD                        := true

# Tool
TW_ENABLE_ALL_PARTITION_TOOLS := true
TW_INCLUDE_7ZA                := true
# Repack tools are intentionally omitted; this removes the obsolete Install Kernel UI.
TW_INCLUDE_RESETPROP          := true
TW_USE_TOOLBOX                := true

# TWRP advanced features
TW_INCLUDE_ADB_BACKUP       := true
TW_INCLUDE_BLOBPACK         := true
TW_INCLUDE_MTP              := true
TW_INCLUDE_SELINUX          := true
TW_INCLUDE_SEPOLICY         := true
TW_INCLUDE_ZIP              := true
TW_MTP_DEVICE               := "/dev/mtp_usb"
TW_USE_NEW_MINADBD          := true
TW_USE_SHA2                 := true
TW_USE_TWTOOLS              := true

# TWRP display
TW_BRIGHTNESS_PATH := "/sys/class/backlight/panel0-backlight/brightness"
TW_DEFAULT_BRIGHTNESS := 2047
TW_FRAMERATE := 60
TW_MAX_BRIGHTNESS := 4094
TW_SCREEN_TIMEOUT := 120
#TW_SCREEN_BLANK_ON_BOOT := true
TW_THEME := portrait_hdpi
TARGET_USES_VULKAN := true

# TWRP file system
RECOVERY_SDCARD_ON_DATA     := true
TARGET_USES_MKE2FS          := true
TW_ENABLE_FS_COMPRESSION    := true
TW_INCLUDE_FUSE_EXFAT       := true
TW_INCLUDE_FUSE_NTFS        := true
TW_INCLUDE_NTFS_3G          := true
TW_NO_EXFAT_FUSE            := true
TW_BACKUP_EXCLUSIONS        += /data/cache /data/dalvik-cache /data/misc_ce/*/cache /data/system/dropbox
TW_BACKUP_SELINUX_CONTEXTS  := true

# TWRP Wi-Fi
TW_INCLUDE_WIFI := true
TW_WIFI_CTRL_INTERFACE := /tmp/recovery/sockets
TW_WIFI_SUPPLICANT_CONF := /vendor/etc/wifi/wpa_supplicant.conf

# Version
PLATFORM_VERSION := 99.87.36
PLATFORM_VERSION_LAST_STABLE := $(PLATFORM_VERSION)
PLATFORM_SECURITY_PATCH := 2099-12-31
VENDOR_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)
BOOT_SECURITY_PATCH := $(PLATFORM_SECURITY_PATCH)
TW_DEVICE_VERSION := OnePlus_15

# Verified Boot
BOARD_AVB_ENABLE := true

# Vibrator
TW_SUPPORT_INPUT_AIDL_HAPTICS := true

# Other TWRP Configurations
TARGET_RECOVERY_QCOM_RTC_FIX            := true
TW_CUSTOM_CPU_TEMP_PATH                 := "/sys/class/thermal/thermal_zone45/temp" # CPU-0-0-0
TW_EXCLUDE_APEX                         := true
TW_EXCLUDE_DEFAULT_USB_INIT             := true
TW_EXCLUDE_TWRP_APP                     := true
TW_DEFAULT_LANGUAGE                     := en
TW_EXTRA_LANGUAGES                      := true
TW_LOAD_VENDOR_MODULES_EXCLUDE_GKI      := true
TW_USE_SERIALNO_PROPERTY_FOR_DEVICE_ID  := true
TW_QCOM_ATS_OFFSET                      := 1000000000
TW_INCLUDE_LPTOOLS                      := true
TW_INCLUDE_BASH                         := true
TW_INCLUDE_NANO                         := true
TW_INCLUDE_TZDATA                       := true
TW_INCLUDE_CHARGER                      := true
TW_INCLUDE_CRASHLOG                     := true

# Keep TWRP's normal module loader focused only on modules that actually exist
# in the recovery ramdisk vendor module path. Touch-panel modules are loaded by
# /system/bin/twrp-touch-start, and WLAN modules are loaded by
# /system/bin/twrp-wifi-start after CNSS fs_ready is asserted.
TW_LOAD_VENDOR_MODULES := "q6_pdr_dlkm.ko"
TW_POST_DECRYPT_MODULES := ""
