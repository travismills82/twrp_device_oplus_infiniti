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

# Theme
TW_STATUS_ICONS_ALIGN   := center
