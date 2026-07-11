#!/usr/bin/env bash
# Validate that custom recovery helper module identities match their permanent
# unversioned runtime filenames.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
ANDROID_MK="$TREE/Android.mk"
DEVICE_MK="$TREE/device.mk"
TWRP_FLAGS="$TREE/recovery/root/system/etc/twrp.flags"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

modules=(
    twrp-root-patcher
    twrp-wifi-start
    twrp-smb-mount
    twrp-decrypt-prereqs
)

[ -f "$ANDROID_MK" ] || fail "Android.mk was not found"
[ -f "$DEVICE_MK" ] || fail "device.mk was not found"
[ -f "$TWRP_FLAGS" ] || fail "twrp.flags was not found"

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

grep -Fq 'command -v twrp-root-patcher' \
    "$TREE/recovery/root/system/bin/twrp-flash-magisk" ||
    fail "Magisk helper does not resolve twrp-root-patcher"

grep -Fq 'twrp-root-patcher magisk' \
    "$TREE/recovery/root/system/bin/twrp-flash-magisk" ||
    fail "Magisk helper does not invoke twrp-root-patcher"

grep -Fq 'twrp-smb-mount mount' "$TREE/README.md" ||
    fail "README no longer documents the twrp-smb-mount runtime command"

grep -Fq 'WITH_BUNDLED_MAGISK ?= true' "$DEVICE_MK" ||
    fail "bundled Magisk is not the default recovery build mode"

grep -Fq 'PRODUCT_PACKAGES += bundled-magisk-apk' "$DEVICE_MK" ||
    fail "bundled Magisk package is not selected by device.mk"

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

echo "[verified] helper module names are unversioned"
echo "[verified] PRODUCT_PACKAGES entries match Android.mk declarations"
echo "[verified] installed helper filenames and runtime consumers remain unchanged"
echo "[verified] bundled Magisk is the default recovery payload"
echo "[verified] no custom CIFS payloads are staged by the device tree"
echo "[verified] raw userdata image is absent while file-level Data backup remains"
