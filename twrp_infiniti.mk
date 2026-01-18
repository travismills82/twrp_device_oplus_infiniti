#
# Copyright (C) 2025 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/oplus/infiniti

# Inherit from device.mk configuration
$(call inherit-product, $(DEVICE_PATH)/device.mk)

## Device identifier
PRODUCT_DEVICE  := infiniti
PRODUCT_NAME    := twrp_infiniti
PRODUCT_BRAND   := oplus
TARGET_OTA_ASSERT_DEVICE := PLK110,OP611FL1,OP60FFL1,CPH2745,CPH2747,CPH2749

# Theme
TW_STATUS_ICONS_ALIGN   := center
TW_CUSTOM_CLOCK_POS := 65
TW_CUSTOM_CPU_POS := 240
TW_CUSTOM_BATTERY_POS := 790
