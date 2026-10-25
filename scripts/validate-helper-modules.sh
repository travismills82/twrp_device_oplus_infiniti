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
    twrp-charging
    twrp-decrypt-prereqs
    twrp-active-hal
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

if grep -Fq 'PRIMARY_TEMP_PATH=' "$thermal_guard"; then
    fail "thermal guard must not use a fixed thermal-zone number"
fi
grep -Fq 'type="$(cat "${zone%/temp}/type" 2>/dev/null)" || continue' "$thermal_guard" ||
    fail "thermal guard does not identify CPU sensors by thermal-zone type"
grep -Fq 'cpu-*) ;;' "$thermal_guard" ||
    fail "thermal guard does not restrict readings to CPU thermal sensors"
grep -Fq '*trip*) continue ;;' "$thermal_guard" ||
    fail "thermal guard does not exclude fixed CPU trip thresholds"
grep -Eq '^TW_CUSTOM_CPU_TEMP_PATH[[:space:]]*:?=[[:space:]]*"/sys/class/thermal"$' "$TREE/BoardConfig.mk" ||
    fail "recovery UI does not use dynamic CPU thermal discovery"

cpu_temp_patch="$TREE/patches/bootable-recovery/0024-data-discover-cpu-thermal-zones.patch"
[ -f "$cpu_temp_patch" ] ||
    fail "dynamic CPU thermal discovery patch is missing"
grep -Fq 'read_cpu_temperature_directory' "$cpu_temp_patch" ||
    fail "dynamic CPU thermal discovery patch lacks directory scanning"
grep -Fq 'type.find("trip")' "$cpu_temp_patch" ||
    fail "dynamic CPU thermal discovery patch does not exclude trip thresholds"

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

sh -n "$wifi_helper" || fail "Wi-Fi runtime helper has invalid shell syntax"
python3 "$TREE/scripts/test-wifi-runtime-firmware.py" ||
    fail "Wi-Fi active-slot firmware verifier failed"

grep -Fq 'SYSTEM_DLKM_MOUNT="/tmp/system_dlkm"' "$wifi_helper" ||
    fail "Wi-Fi helper does not mount active system_dlkm for rfkill"
grep -Fq 'load_module_at_path rfkill.ko "$SYSTEM_DLKM_MOUNT/lib/modules/rfkill.ko"' "$wifi_helper" ||
    fail "Wi-Fi helper does not source rfkill from active system_dlkm"
grep -Fq 'not loading rfkill.ko without the active system_dlkm provider' "$wifi_helper" ||
    fail "Wi-Fi helper can fall back to an incompatible bundled rfkill module"

grep -Fq 'WITH_BUNDLED_MAGISK ?= true' "$DEVICE_MK" ||
    fail "bundled Magisk is not the default recovery build mode"

grep -Fq 'PRODUCT_PACKAGES += bundled-magisk-apk' "$DEVICE_MK" ||
    fail "bundled Magisk package is not selected by device.mk"

grep -Eq '^[[:space:]]*init\.recovery\.mksh\.rc([[:space:]]*\\)?[[:space:]]*$' "$DEVICE_MK" ||
    fail "init.recovery.mksh.rc is not selected for the recovery ramdisk"

decrypt_helper="$TREE/recovery/root/system/bin/twrp-decrypt-prereqs"
active_hal="$TREE/recovery/root/system/bin/twrp-active-hal"
active_hal_linker_config="$TREE/recovery/root/system/etc/twrp-active-hal.ld.config.txt"
[ -x "$active_hal" ] || fail "active HAL launcher is missing or not executable"
[ -f "$active_hal_linker_config" ] || fail "active HAL linker configuration is missing"

grep -Fq 'LOCAL_MODULE := twrp-active-hal-linker-config' "$ANDROID_MK" ||
    fail "active HAL linker configuration is not packaged"
grep -Eq '^[[:space:]]*twrp-active-hal-linker-config([[:space:]]*\\)?[[:space:]]*$' "$DEVICE_MK" ||
    fail "active HAL linker configuration is not selected"

for expected in \
    'set_status loading-nfc-transport' \
    'load_nxp_nci_module' \
    'prepare_active_nfc_runtime || fail_prereq nfc-runtime-unavailable' \
    'prepare_coloros17_active_runtime()' \
    'mount_active_partition vendor "$ACTIVE_VENDOR_MOUNT"' \
    'mount_active_partition system "$ACTIVE_SYSTEM_MOUNT"' \
    'mount_active_partition odm "$ACTIVE_ODM_MOUNT"' \
    'android.hardware.nfc2-service.nxp' \
    'nfc_nci_nxp_snxxx_v2.so' \
    'COLOROS_NFC_CONFIG="/odm/etc/libnfc-nci.conf"' \
    'COLOROS_NFC_CONFIG_DIR="/odm/etc/nfc"' \
    'nfc_nci_nxp_snxxx.so'; do
    grep -Fq "$expected" "$decrypt_helper" ||
        fail "Lineage active-slot decrypt runtime is missing: $expected"
done

load_line="$(grep -n '^load_nxp_nci_module$' "$decrypt_helper" | tail -n1 | cut -d: -f1)"
runtime_line="$(grep -n '^prepare_active_nfc_runtime || fail_prereq nfc-runtime-unavailable' "$decrypt_helper" | cut -d: -f1)"
[ -n "$load_line" ] && [ -n "$runtime_line" ] && [ "$load_line" -lt "$runtime_line" ] ||
    fail "NXP NCI module is not loaded before active runtime selection"

for expected in \
    'export LD_CONFIG_FILE="$ACTIVE_LINKER_CONFIG"' \
    'unset LD_LIBRARY_PATH LD_PRELOAD' \
    '$ACTIVE_ODM_MOUNT/bin/hw/android.hardware.nfc2-service.nxp' \
    '/odm/bin/hw/android.hardware.nfc-service.nxp' \
    '/vendor/bin/hw/android.hardware.secure_element-service.qti' \
    '/odm/bin/hw/android.hardware.weaver-service.nxp'; do
    grep -Fq "$expected" "$active_hal" ||
        fail "active HAL launcher is missing its expected runtime path: $expected"
done

for expected in \
    'dir.twrp_active_vendor = /tmp/twrp-crypto-vendor/bin' \
    'dir.twrp_active_odm = /tmp/twrp-crypto-odm/bin' \
    '[twrp_active_vendor]' \
    '[twrp_active_odm]' \
    'namespace.default.search.paths += /tmp/twrp-crypto-vendor/lib64/hw' \
    'namespace.system.search.paths = /tmp/twrp-crypto-system/system/lib64'; do
    grep -Fq "$expected" "$active_hal_linker_config" ||
        fail "active HAL linker configuration is missing: $expected"
done

vendor_dir_line="$(grep -n '^dir.twrp_active_vendor' "$active_hal_linker_config" | cut -d: -f1)"
odm_dir_line="$(grep -n '^dir.twrp_active_odm' "$active_hal_linker_config" | cut -d: -f1)"
recovery_section_line="$(grep -n '^\[recovery\]$' "$active_hal_linker_config" | cut -d: -f1)"
[ "$vendor_dir_line" -lt "$recovery_section_line" ] && [ "$odm_dir_line" -lt "$recovery_section_line" ] ||
    fail "active HAL linker directories must precede linker sections"

grep -Fq 'service vendor.nfc_hal_service /system/bin/twrp-active-hal nfc' \
    "$TREE/recovery/root/vendor/odm/etc/init/nfc-service-nxp.rc" ||
    fail "NFC service does not use the active HAL launcher"
grep -Fq 'service vendor.secure_element /system/bin/twrp-active-hal secure-element' \
    "$TREE/recovery/root/vendor/etc/init/android.hardware.secure_element-service.qti.rc" ||
    fail "secure-element service does not use the active HAL launcher"
grep -Fq 'service vendor.weaver_nxp /system/bin/twrp-active-hal weaver' \
    "$TREE/recovery/root/vendor/odm/etc/init/android.hardware.weaver-service.nxp.rc" ||
    fail "Weaver service does not use the active HAL launcher"

sh -n "$decrypt_helper" || fail "decrypt prerequisite helper has invalid shell syntax"
sh -n "$active_hal" || fail "active HAL launcher has invalid shell syntax"

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
echo "[verified] Wi-Fi firmware is linked read-only from the active phone slot"
echo "[verified] bundled Magisk is the default recovery payload"
echo "[verified] no custom CIFS payloads are staged by the device tree"
echo "[verified] raw userdata image is absent while file-level Data backup remains"
echo "[verified] recovery init avoids unsupported commands, missing ADSP waits, and duplicate FunctionFS mounts"
echo "[verified] recovery includes mksh init support and no missing optional uevent imports"
echo "[verified] TWRP-only backup flags are isolated from Android fstab parsing"
