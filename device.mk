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
	twrp-load-wifi

# Recovery Wi-Fi userspace tools
PRODUCT_PACKAGES += \
	wpa_supplicant \
	wpa_cli

ifneq ($(wildcard $(DEVICE_PATH)/prebuilts/magisk/Magisk.apk),)
PRODUCT_PACKAGES += bundled-magisk-apk
endif

# Soong namespaces
PRODUCT_SOONG_NAMESPACES += $(DEVICE_PATH)
