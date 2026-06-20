#
# Copyright (C) 2026 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-dynamic-flash-helper
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-dynamic-flash-helper
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-partition-backup
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-partition-backup
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-recovery-tools
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-recovery-tools
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-root-patcher-v2
LOCAL_MODULE_STEM := twrp-root-patcher
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-root-patcher
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-magisk-bundled
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-magisk-bundled
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-flash-magisk
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-flash-magisk
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-wifi-start-v2
LOCAL_MODULE_STEM := twrp-wifi-start
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-wifi-start
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-dhcpcd-run-hooks
LOCAL_MODULE_STEM := dhcpcd-run-hooks
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/etc/dhcpcd/dhcpcd-run-hooks
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/etc/dhcpcd
LOCAL_POST_INSTALL_CMD := chmod 0755 $(LOCAL_INSTALLED_MODULE)
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-resolv-conf
LOCAL_MODULE_STEM := resolv.conf
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := ETC
LOCAL_SRC_FILES := recovery/root/system/etc/resolv.conf
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/etc
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-ping
LOCAL_MODULE_STEM := ping
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/ping
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-smb-mount-v1
LOCAL_MODULE_STEM := twrp-smb-mount
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-smb-mount
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-touch-start
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-touch-start
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

include $(CLEAR_VARS)
LOCAL_MODULE := twrp-decrypt-prereqs-v2
LOCAL_MODULE_STEM := twrp-decrypt-prereqs
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := EXECUTABLES
LOCAL_SRC_FILES := recovery/root/system/bin/twrp-decrypt-prereqs
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/bin
include $(BUILD_PREBUILT)

ifneq ($(wildcard $(LOCAL_PATH)/prebuilts/magisk/Magisk.apk),)
include $(CLEAR_VARS)
LOCAL_MODULE := bundled-magisk-apk
LOCAL_MODULE_TAGS := optional
LOCAL_MODULE_CLASS := ETC
LOCAL_SRC_FILES := prebuilts/magisk/Magisk.apk
LOCAL_MODULE_PATH := $(TARGET_RECOVERY_ROOT_OUT)/system/etc/magisk
LOCAL_MODULE_STEM := Magisk.apk
include $(BUILD_PREBUILT)
endif
