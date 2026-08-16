#!/usr/bin/env bash
# Validate that custom recovery helper module identities match their permanent
# unversioned runtime filenames.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
ANDROID_MK="$TREE/Android.mk"
DEVICE_MK="$TREE/device.mk"
TWRP_FLAGS="$TREE/recovery/root/system/etc/twrp.flags"
QCOM_INIT_RC="$TREE/recovery/root/init.recovery.qcom.rc"
USB_INIT_RC="$TREE/recovery/root/init.recovery.usb.rc"
RECOVERY_FSTAB="$TREE/recovery.fstab"
RECOVERY_ROOT_FSTAB="$TREE/recovery/root/system/etc/recovery.fstab"
UEVENTD_RC="$TREE/recovery/root/system/etc/ueventd.rc"
VENDOR_UEVENTD_RC="$TREE/recovery/root/vendor/etc/ueventd.rc"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

modules=(
    twrp-flash-kernel
    twrp-flash-controlled-stack
    twrp-root-patcher
    twrp-wifi-start
    twrp-smb-mount
    twrp-thermal-guard
    twrp-decrypt-prereqs
)

[ -f "$ANDROID_MK" ] || fail "Android.mk was not found"
[ -f "$DEVICE_MK" ] || fail "device.mk was not found"
[ -f "$TWRP_FLAGS" ] || fail "twrp.flags was not found"
[ -f "$QCOM_INIT_RC" ] || fail "init.recovery.qcom.rc was not found"
[ -f "$USB_INIT_RC" ] || fail "init.recovery.usb.rc was not found"
[ -f "$RECOVERY_FSTAB" ] || fail "recovery.fstab was not found"
[ -f "$RECOVERY_ROOT_FSTAB" ] || fail "packaged recovery.fstab was not found"
[ -f "$UEVENTD_RC" ] || fail "recovery ueventd.rc was not found"
[ -f "$VENDOR_UEVENTD_RC" ] || fail "recovery vendor ueventd.rc was not found"

for module in "${modules[@]}"; do
    declaration_count="$(grep -Fxc "LOCAL_MODULE := $module" "$ANDROID_MK" || true)"
    [ "$declaration_count" -eq 1 ] ||
        fail "expected one LOCAL_MODULE declaration for $module; found $declaration_count"

    package_count="$(grep -Ec "^[[:space:]]*${module}([[:space:]]*\\\\)?[[:space:]]*$" "$DEVICE_MK" || true)"
    [ "$package_count" -eq 1 ] ||
        fail "expected one PRODUCT_PACKAGES entry for $module; found $package_count"

    source="$TREE/recovery/root/system/bin/$module"
    [ -f "$source" ] || fail "runtime helper source is missing: ${source#"$TREE/"}"

    if grep -Fqx "LOCAL_MODULE_STEM := $module" "$ANDROID_MK"; then
        fail "redundant LOCAL_MODULE_STEM remains for $module"
    fi

done

scan_paths=(
    "$ANDROID_MK"
    "$DEVICE_MK"
    "$TREE/README.md"
    "$TREE/.github"
    "$TREE/scripts"
    "$TREE/tools"
    "$TREE/recovery/root"
)

suffix_pattern='twrp-(root-patcher|wifi-start|smb-mount|decrypt-prereqs)-v[0-9]+'
if grep -RInI -E "$suffix_pattern" "${scan_paths[@]}" 2>/dev/null; then
    fail "version-suffixed helper module reference remains"
fi

# Verify the important runtime consumers still use the unversioned installed
# paths after the module-identity cleanup.
grep -Fq 'service twrp-wifi-start /system/bin/twrp-wifi-start' \
    "$TREE/recovery/root/init.recovery.wifi.rc" ||
    fail "Wi-Fi init service does not use /system/bin/twrp-wifi-start"

thermal_guard="$TREE/recovery/root/system/bin/twrp-thermal-guard"
[ -f "$thermal_guard" ] || fail "thermal guard source is missing"

grep -Fq 'LOCAL_POST_INSTALL_CMD = chmod 0755 $(LOCAL_INSTALLED_MODULE)' "$ANDROID_MK" ||
    fail "thermal guard is not installed as an executable"

grep -Fq 'service twrp-thermal-guard /system/bin/twrp-thermal-guard' "$QCOM_INIT_RC" ||
    fail "thermal guard init service is missing"

grep -Fq 'start twrp-thermal-guard' "$QCOM_INIT_RC" ||
    fail "thermal guard is not started during recovery init"

grep -Fqx 'POLL_SECONDS=1' "$thermal_guard" ||
    fail "thermal guard does not poll once per second"

grep -Fqx 'NORMAL_BRIGHTNESS=preserve' "$thermal_guard" ||
    fail "thermal guard does not preserve normal TWRP brightness"

grep -Fq 'write /sys/class/backlight/panel0-backlight/brightness 2047' "$QCOM_INIT_RC" ||
    fail "recovery init does not use the configured default screen brightness"

grep -Fqx 'TW_SCREEN_TIMEOUT := 120' "$TREE/BoardConfig.mk" ||
    fail "recovery screen timeout is not enabled"

grep -Fqx 'TW_INCLUDE_ZSTD               := true' "$TREE/BoardConfig.mk" ||
    fail "recovery does not package the zstd backup compressor"

grep -Eq '^BOARD_AVB_ENABLE[[:space:]]*:?=[[:space:]]*true$' "$TREE/BoardConfig.mk" ||
    fail "standalone recovery is not configured to add its required AVB footer"

grep -Eq '^BOARD_AVB_RECOVERY_KEY_PATH[[:space:]]*:?=[[:space:]]*external/avb/test/data/testkey_rsa2048\.pem$' "$TREE/BoardConfig.mk" ||
    fail "standalone recovery does not use the verifiable AVB signing key"

grep -Eq '^BOARD_AVB_RECOVERY_ALGORITHM[[:space:]]*:?=[[:space:]]*SHA256_RSA2048$' "$TREE/BoardConfig.mk" ||
    fail "standalone recovery AVB signing algorithm is not SHA256_RSA2048"

if grep -Eq '^BOARD_QTI_DYNAMIC_PARTITIONS_PARTITION_LIST.*system_dlkm_oki' "$TREE/BoardConfig.mk"; then
    fail "system_dlkm_oki must remain a recovery-only logical target, not a generated super-image partition"
fi

lpdump_runtime_patch="$TREE/patches/bootable-recovery/0015-lpdump-package-runtime-dependencies.patch"
[ -f "$lpdump_runtime_patch" ] ||
    fail "lpdump recovery runtime dependency patch is missing"
grep -Fq '+        RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/libfs_mgr_binder.so' \
    "$lpdump_runtime_patch" ||
    fail "lpdump recovery runtime dependency patch does not package libfs_mgr_binder"
grep -Fq '+        RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/libsnapshot.so' \
    "$lpdump_runtime_patch" ||
    fail "lpdump recovery runtime dependency patch does not package libsnapshot"
grep -Fq '+LOCAL_ADDITIONAL_DEPENDENCIES += $(TARGET_OUT_SHARED_LIBRARIES)/liblpdump.so' \
    "$lpdump_runtime_patch" ||
    fail "lpdump recovery runtime dependency patch lacks library refresh dependencies"

lpdump_relink_patch="$TREE/patches/bootable-recovery/0016-lpdump-refresh-incremental-recovery-stage.patch"
[ -f "$lpdump_relink_patch" ] ||
    fail "lpdump incremental recovery staging patch is missing"
grep -Fq '+LOCAL_ADDITIONAL_DEPENDENCIES += $(TARGET_OUT_EXECUTABLES)/lpdump $(TARGET_OUT_EXECUTABLES)/lpdumpd' \
    "$lpdump_relink_patch" ||
    fail "lpdump incremental recovery staging patch lacks the client dependencies"

grep -Fq '[ "$temp" -ge 80000 ]' "$thermal_guard" ||
    fail "thermal guard critical threshold is not 80C"

grep -Fq 'command -v twrp-root-patcher' \
    "$TREE/recovery/root/system/bin/twrp-flash-magisk" ||
    fail "Magisk helper does not resolve twrp-root-patcher"

grep -Fq 'twrp-root-patcher magisk' \
    "$TREE/recovery/root/system/bin/twrp-flash-magisk" ||
    fail "Magisk helper does not invoke twrp-root-patcher"

kernel_flash="$TREE/recovery/root/system/bin/twrp-flash-kernel"
controlled_stack="$TREE/recovery/root/system/bin/twrp-flash-controlled-stack"
grep -Fqx 'MODE=--dry-run' "$kernel_flash" ||
    fail "legacy kernel flash front end must default to a dry run"
grep -Fq 'twrp-flash-controlled-stack' "$kernel_flash" ||
    fail "legacy kernel flash front end does not delegate to the controlled-stack helper"
grep -Fqx 'MODE=dry-run' "$controlled_stack" ||
    fail "controlled-stack helper must default to a dry run"
grep -Fq 'lpdump --slot "$slot"' "$controlled_stack" ||
    fail "controlled-stack helper does not inspect the active slot metadata"
grep -Fq 'Update state: none' "$controlled_stack" ||
    fail "controlled-stack helper does not reject active snapshot updates"
grep -Fq '/dev/block/bootdevice/by-name/boot${slot}' "$controlled_stack" ||
    fail "controlled-stack helper does not target the active boot slot"
grep -Fq '/dev/block/bootdevice/by-name/vendor_boot${slot}' "$controlled_stack" ||
    fail "controlled-stack helper does not target the active vendor_boot slot"
grep -Fq '/dev/block/mapper/system_dlkm${slot}' "$controlled_stack" ||
    fail "controlled-stack helper does not target the active system_dlkm mapper"
grep -Fq '/dev/block/mapper/vendor_dlkm${slot}' "$controlled_stack" ||
    fail "controlled-stack helper does not target the active vendor_dlkm mapper"
grep -Fq 'VENDOR_DLKM_FORMAT=' "$controlled_stack" ||
    fail "controlled-stack helper does not track vendor_dlkm image format"
grep -Fq 'erofs_magic' "$controlled_stack" ||
    fail "controlled-stack helper does not verify the EROFS superblock"
grep -Fq 'backup checksum mismatch' "$controlled_stack" ||
    fail "controlled-stack helper does not verify backup source checksums"
grep -Fq 'system_dlkm_oki is intentionally not touched' "$controlled_stack" ||
    fail "controlled-stack helper must document that system_dlkm_oki is untouched"
grep -Fq 'require_canoe_cph2747' "$controlled_stack" ||
    fail "controlled-stack helper lacks the CPH2747 device guard"
grep -Fq 'Dependency-first ordering' "$controlled_stack" ||
    fail "controlled-stack helper does not document dependency-first ordering"

grep -Fq 'patch_twrp_magisk_theme.py' "$ANDROID_MK" ||
    fail "recovery build does not patch the Advanced helper menus"

grep -Fq 'twrp-smb-mount mount' "$TREE/README.md" ||
    fail "README no longer documents the twrp-smb-mount runtime command"

wifi_helper="$TREE/recovery/root/system/bin/twrp-wifi-start"
vendor_dlkm_cleanup_count="$(grep -Fxc '    rm -f /tmp/twrp-wifi-vendor-dlkm.err' "$wifi_helper" || true)"
[ "$vendor_dlkm_cleanup_count" -eq 2 ] ||
    fail "Wi-Fi vendor_dlkm fallback errors are not cleared before and after success"

grep -Fq 'WITH_BUNDLED_MAGISK ?= true' "$DEVICE_MK" ||
    fail "bundled Magisk is not the default recovery build mode"

grep -Fq 'PRODUCT_PACKAGES += bundled-magisk-apk' "$DEVICE_MK" ||
    fail "bundled Magisk package is not selected by device.mk"

grep -Eq '^[[:space:]]*init\.recovery\.mksh\.rc([[:space:]]*\\)?[[:space:]]*$' "$DEVICE_MK" ||
    fail "init.recovery.mksh.rc is not selected for the recovery ramdisk"

magisk_apk="$TREE/prebuilts/magisk/Magisk.apk"
[ -f "$magisk_apk" ] || fail "bundled Magisk APK is missing"

cifs_payloads=(
    cifs.ko
    cifs_arc4.ko
    cifs_md4.ko
    dns_resolver.ko
    netfs.ko
    nls_ucs2_utils.ko
)

for payload in "${cifs_payloads[@]}"; do
    if find "$TREE/recovery/root" -type f -name "$payload" -print -quit | grep -q .; then
        fail "custom CIFS payload remains in the recovery ramdisk: $payload"
    fi
done

# The file-level Data backup lives on data-media.  Do not expose userdata as a
# raw backup image as doing so makes TWRP reserve the whole destination volume.
if grep -Eq '^[[:space:]]*/userdata_image([[:space:]]|$)' "$TWRP_FLAGS" ||
    grep -Fq 'display="Data Image"' "$TWRP_FLAGS"; then
    fail "raw userdata image target must not be exposed in twrp.flags"
fi

grep -Eq '^[[:space:]]*/data[[:space:]]+f2fs[[:space:]].*display="Data";backup=1' "$TWRP_FLAGS" ||
    fail "file-level Data backup is missing from twrp.flags"

if grep -Eq '^[[:space:]]*setenforce[[:space:]]' "$QCOM_INIT_RC"; then
    fail "init.recovery.qcom.rc uses the unsupported Android init setenforce command"
fi

if grep -Fq '/sys/kernel/boot_adsp/ssr' "$QCOM_INIT_RC"; then
    fail "init.recovery.qcom.rc still waits for the nonexistent boot_adsp/ssr node"
fi

if grep -Eq '^[[:space:]]*mount functionfs (adb|fastboot)[[:space:]]' "$USB_INIT_RC"; then
    fail "init.recovery.usb.rc duplicates base recovery FunctionFS mounts"
fi

grep -Eq '^[[:space:]]*mount functionfs mtp[[:space:]]' "$USB_INIT_RC" ||
    fail "init.recovery.usb.rc no longer mounts its MTP FunctionFS endpoint"

if grep -Fq 'import /odm/etc/ueventd.wifi.rc' "$UEVENTD_RC"; then
    fail "recovery ueventd.rc imports unavailable vendor Wi-Fi BDF rules"
fi

if grep -Fq 'import /vendor/etc/ueventd.qcom.userdebug.rc' "$VENDOR_UEVENTD_RC"; then
    fail "recovery vendor ueventd.rc imports unavailable userdebug rules"
fi

for fstab in "$RECOVERY_FSTAB" "$RECOVERY_ROOT_FSTAB"; do
    if grep -Eq '(^|,)(backup=1|flashimg=1|display=|resize)' "$fstab"; then
        fail "Android fstab still contains TWRP-only backup or display flags: ${fstab#"$TREE/"}"
    fi
done

for target in boot init_boot vendor_boot dtbo recovery; do
    grep -Eq "^[[:space:]]*/${target}[[:space:]]+emmc[[:space:]].*flags=.*backup=1;flashimg=1" "$TWRP_FLAGS" ||
        fail "TWRP backup flags are missing for /${target}"
done

echo "[verified] helper module names are unversioned"
echo "[verified] PRODUCT_PACKAGES entries match Android.mk declarations"
echo "[verified] installed helper filenames and runtime consumers remain unchanged"
echo "[verified] recovery thermal guard is packaged, starts at init, and polls at one-second intervals"
echo "[verified] recovery packages zstd for selectable file-based backup compression"
echo "[verified] standalone recovery is configured with the required AVB hash footer"
echo "[verified] recovery build patches Advanced with Magisk, FTP, and AVB menus"
echo "[verified] Wi-Fi vendor_dlkm fallback does not leave stale error artifacts"
echo "[verified] bundled Magisk is the default recovery payload"
echo "[verified] no custom CIFS payloads are staged by the device tree"
echo "[verified] raw userdata image is absent while file-level Data backup remains"
echo "[verified] recovery init avoids unsupported commands, missing ADSP waits, and duplicate FunctionFS mounts"
echo "[verified] recovery includes mksh init support and no missing optional uevent imports"
echo "[verified] TWRP-only backup flags are isolated from Android fstab parsing"
