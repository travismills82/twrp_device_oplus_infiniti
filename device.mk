#
# Copyright (C) 2025 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Configure base.mk
$(call inherit-product, $(SRC_TARGET_DIR)/product/base.mk)

# Configure core_64_bit_only.mk
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)

# Configure virtual_ab compression.mk
$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota/compression_with_xor.mk)

# Configure emulated_storage.mk
$(call inherit-product, $(SRC_TARGET_DIR)/product/emulated_storage.mk)

# Configure twrp common.mk
$(call inherit-product, vendor/twrp/config/common.mk)

# Shipping API level
BOARD_SHIPPING_API_LEVEL    := 36
PRODUCT_SHIPPING_API_LEVEL  := 36
PRODUCT_TARGET_VNDK_VERSION := 36

# Dynamic partitions
PRODUCT_USE_DYNAMIC_PARTITIONS := true

# Kernel
PRODUCT_OTA_ENFORCE_VINTF_KERNEL_REQUIREMENTS   := false
PRODUCT_ENABLE_UFFD_GC                          := true

PRODUCT_CHECK_PREBUILT_MAX_PAGE_SIZE := false

# OTA certs
PRODUCT_EXTRA_RECOVERY_KEYS += \
	$(DEVICE_PATH)/security/local_OTA \
	$(DEVICE_PATH)/security/special_OTA

# Recovery helpers
PRODUCT_PACKAGES += \
	twrp-dynamic-flash-helper \
	twrp-partition-backup \
	twrp-recovery-tools \
	twrp-root-patcher \
	twrp-magisk-bundled \
	twrp-flash-magisk \
	twrp-wifi-start \
	twrp-touch-start

# Recovery Wi-Fi userspace tools
PRODUCT_PACKAGES += \
	wpa_supplicant \
	wpa_cli

# Keep prebuilt WLAN and touch modules visible even after /vendor is mounted over the ramdisk vendor folder.
PRODUCT_COPY_FILES += \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/qmi_helpers.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/qmi_helpers.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cnss_prealloc.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cnss_prealloc.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cnss_utils.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cnss_utils.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cnss_plat_ipc_qmi_svc.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cnss_plat_ipc_qmi_svc.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cnss_nl.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cnss_nl.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/wlan_firmware_service.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/wlan_firmware_service.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cnss2.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cnss2.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/rmnet_mem.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/rmnet_mem.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/gsim.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/gsim.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/ipam.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/ipam.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/rfkill.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/rfkill.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/cfg80211.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/cfg80211.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/qca_cld3_peach_v2.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/qca_cld3_peach_v2.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_synaptics_tcm2.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_synaptics_tcm2.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_common.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_common.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_custom.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_custom.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_focal_common.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_focal_common.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ft3518.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ft3518.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ft3658u_spi.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ft3658u_spi.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ft3681.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ft3681.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ft3683g.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ft3683g.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ft8057p.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ft8057p.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_goodix_comnon.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_goodix_comnon.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_gt9916.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_gt9916.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_gt9966.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_gt9966.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ilitek7807s.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ilitek7807s.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_ilitek_common.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_ilitek_common.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_notify.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_notify.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_novatek_common.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_novatek_common.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_nt36528_noflash.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_nt36528_noflash.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_nt36532_noflash.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_nt36532_noflash.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_nt36672c_noflash.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_nt36672c_noflash.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_syna_common.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_syna_common.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_tcm_S3908.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_tcm_S3908.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_tcm_S3910.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_tcm_S3910.ko \
	$(DEVICE_PATH)/recovery/root/vendor/lib/modules/oplus_bsp_tp_td4377_noflash.ko:$(TARGET_COPY_OUT_RECOVERY)/root/system/lib/modules/oplus_bsp_tp_td4377_noflash.ko

ifneq ($(wildcard $(DEVICE_PATH)/prebuilts/magisk/Magisk.apk),)
PRODUCT_PACKAGES += bundled-magisk-apk
endif

# Soong namespaces
PRODUCT_SOONG_NAMESPACES += $(DEVICE_PATH)
