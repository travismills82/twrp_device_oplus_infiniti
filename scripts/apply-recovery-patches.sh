#!/usr/bin/env bash
#
# Apply device-required patches to the TWRP recovery source checkout.
#
# Usage:
#   device/oplus/infiniti/scripts/apply-recovery-patches.sh
#   device/oplus/infiniti/scripts/apply-recovery-patches.sh /path/to/source/root
#

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEVICE_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
DEFAULT_SOURCE_ROOT="$(CDPATH= cd -- "$DEVICE_DIR/../../.." && pwd)"
SOURCE_ROOT="${1:-$DEFAULT_SOURCE_ROOT}"
RECOVERY_DIR="$SOURCE_ROOT/bootable/recovery"
PATCH_DIR="$DEVICE_DIR/patches/bootable-recovery"
SYSTEM_CORE_DIR="$SOURCE_ROOT/system/core"
SYSTEM_UPDATE_ENGINE_DIR="$SOURCE_ROOT/system/update_engine"
SYSTEM_VOLD_DIR="$SOURCE_ROOT/system/vold"
SYSTEM_EXTRAS_DIR="$SOURCE_ROOT/system/extras"
SYSTEM_CORE_PATCH_DIR="$DEVICE_DIR/patches/system-core"
SYSTEM_UPDATE_ENGINE_PATCH_DIR="$DEVICE_DIR/patches/system-update-engine"
SYSTEM_VOLD_PATCH_DIR="$DEVICE_DIR/patches/system-vold"
SYSTEM_EXTRAS_PATCH_DIR="$DEVICE_DIR/patches/system-extras"
THEME_ASSET_DIR="$DEVICE_DIR/assets/twrp-theme"
HELPER_VALIDATOR="$SCRIPT_DIR/validate-helper-modules.sh"
EXPECTED_BASE="6bd8134ec8ff4cb29eb25797cbb20796f8455204"
PIGZ_TEST_CALL='execlp("pigz", "pigz", "-9", "-", NULL)'
ZSTD_COMPRESS_CALL='execlp("zstd", "zstd", "-q", "-T0", "-11", "-c", NULL)'
ZSTD_DECOMPRESS_CALL='execlp("zstd", "zstd", "-q", "-d", "-c", NULL)'
DNS_PUBLISH_CALL='/system/bin/twrp-dns-publish wlan0 2>&1'
NANDSWAP_EXCLUSION='ExcludeAll(Mount_Point + "/nandswap")'
WIFI_ICON_MARKER='OP15 Wi-Fi status icon START'
WIFI_STATUS_ICON="$RECOVERY_DIR/gui/theme/portrait_hdpi/images/wifi_status.png"
WIFI_STATUS_ICON_B64="$THEME_ASSET_DIR/wifi_status.png.b64"
WIFI_STATUS_PLACEMENT='<placement x="720" y="10"/>'
WLAN_LOGBOX_PLACEMENT='<borderedlogbox toprow="%row1a_y%" bottomrow="%row15_y%"'
ADVANCED_AVB2_ENTRY='<listitem name="{@disable_avb2=Disable AVB2.0}">'
ADVANCED_INSTALL_APP_ENTRY='<listitem name="{@reboot_install_app_hdr=Install TWRP App}">'
FAILED_VAB_SIDELOAD_MARKER='Cancelling failed Virtual A/B update in recovery before sideload.'
LPDUMP_BINDER_LIBRARY='RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/libfs_mgr_binder.so'
LPDUMP_SNAPSHOT_LIBRARY='RECOVERY_LIBRARY_SOURCE_FILES += $(TARGET_OUT_SHARED_LIBRARIES)/libsnapshot.so'
LPDUMP_RELINK_DEPENDENCIES='LOCAL_ADDITIONAL_DEPENDENCIES += $(TARGET_OUT_EXECUTABLES)/lpdump $(TARGET_OUT_EXECUTABLES)/lpdumpd'
LPDUMP_LIBRARY_RELINK_FIRST_LINE='LOCAL_ADDITIONAL_DEPENDENCIES += $(TARGET_OUT_SHARED_LIBRARIES)/liblpdump.so'
LPDUMP_LIBRARY_RELINK_SNAPSHOT_LINE='    $(TARGET_OUT_SHARED_LIBRARIES)/libsnapshot.so'

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -f "$HELPER_VALIDATOR" ] || fail "Helper module validator was not found: $HELPER_VALIDATOR"
bash "$HELPER_VALIDATOR"

[ -d "$RECOVERY_DIR/.git" ] ||
    fail "TWRP recovery source was not found at $RECOVERY_DIR"

[ -f "$WIFI_STATUS_ICON_B64" ] || fail "Wi-Fi status icon source was not found: $WIFI_STATUS_ICON_B64"

command -v git >/dev/null 2>&1 || fail "git is not installed"
command -v base64 >/dev/null 2>&1 || fail "base64 is not installed"
command -v python3 >/dev/null 2>&1 || fail "python3 is not installed"

mapfile -t PATCHES < <(find "$PATCH_DIR" -maxdepth 1 -type f -name '*.patch' | sort)
[ "${#PATCHES[@]}" -gt 0 ] || fail "No recovery patches found in $PATCH_DIR"

REMOTE_URL="$(git -C "$RECOVERY_DIR" remote get-url origin 2>/dev/null || true)"
CURRENT_HEAD="$(git -C "$RECOVERY_DIR" rev-parse HEAD)"

echo "Recovery source: $RECOVERY_DIR"
echo "Remote:          ${REMOTE_URL:-unknown}"
echo "Current HEAD:    $CURRENT_HEAD"
echo "Reference HEAD:  $EXPECTED_BASE"
echo

for patch in "${PATCHES[@]}"; do
    name="$(basename "$patch")"
    apply_opts=()

    # 0007 through 0010 deliberately use zero-context hunks so their tracked
    # artifacts remain whitespace-clean. The modified lines are unique and
    # the script verifies the expected source state before and after applying
    # every patch.
    case "$name" in
        0007-ors-fix-restore-resource-and-cli-help.patch|0008-init-drop-legacy-recovery-service-import.patch|0009-theme-raise-wlan-log-window.patch|0010-theme-remove-advanced-avb-and-app-actions.patch)
            apply_opts+=(--unidiff-zero)
            ;;
    esac

    if ! git apply "${apply_opts[@]}" --numstat "$patch" >/dev/null; then
        fail "Patch syntax validation failed: $name"
    fi

    case "$name" in
        0001-wifi-use-returned-network-id.patch)
            if grep -F -q 'Supplicant network ID' "$RECOVERY_DIR/gui/action.cpp"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
        0002-backup-use-pigz-level-9.patch)
            if [ "$(grep -F -c "$PIGZ_TEST_CALL" "$RECOVERY_DIR/twrpTar.cpp" 2>/dev/null || true)" -eq 2 ] &&
                ! grep -F -q 'execlp("pigz", "pigz", "-", NULL)' "$RECOVERY_DIR/twrpTar.cpp"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
        0004-wifi-publish-dns-from-root-ui.patch)
            if [ "$(grep -F -c "$DNS_PUBLISH_CALL" "$RECOVERY_DIR/gui/action.cpp" 2>/dev/null || true)" -eq 2 ] &&
                grep -F -q 'DNS resolver setup failed' "$RECOVERY_DIR/gui/action.cpp"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
        0006-wifi-show-connected-status-icon.patch)
            if grep -F -q '<image name="wifi_status" filename="wifi_status" retainaspect="1"/>' \
                    "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml" &&
                grep -F -q '<image resource="wifi_status"/>' \
                    "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml" &&
                grep -F -q "$WIFI_STATUS_PLACEMENT" \
                    "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
    esac

    if git -C "$RECOVERY_DIR" apply "${apply_opts[@]}" --reverse --check "$patch" >/dev/null 2>&1; then
        echo "[already applied] $name"
        continue
    fi

    if ! git -C "$RECOVERY_DIR" apply "${apply_opts[@]}" --check "$patch"; then
        echo >&2
        echo "Patch applicability validation failed: $name" >&2
        echo "The recovery checkout may have moved beyond the source revision this patch targets." >&2
        echo "Current HEAD:   $CURRENT_HEAD" >&2
        echo "Reference HEAD: $EXPECTED_BASE" >&2
        exit 1
    fi

    git -C "$RECOVERY_DIR" apply "${apply_opts[@]}" "$patch"
    echo "[applied] $name"
done

if grep -Fq 'import /init.recovery.service.rc' "$RECOVERY_DIR/etc/init.rc"; then
    fail "legacy init.recovery.service.rc import leaves a duplicate recovery service"
fi

grep -Fq "$WIFI_STATUS_PLACEMENT" "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml" ||
    fail "Wi-Fi status icon placement was not updated"

grep -Fq "$WLAN_LOGBOX_PLACEMENT" "$RECOVERY_DIR/gui/theme/common/portrait.xml" ||
    fail "WLAN log window placement was not updated"

if grep -Fq "$ADVANCED_AVB2_ENTRY" "$RECOVERY_DIR/gui/theme/common/portrait.xml"; then
    fail "Advanced menu still exposes the Disable AVB2.0 action"
fi

if grep -Fq "$ADVANCED_INSTALL_APP_ENTRY" "$RECOVERY_DIR/gui/theme/common/portrait.xml"; then
    fail "Advanced menu still exposes the Install TWRP App action"
fi

apply_external_patch_series() {
    local source_dir="$1"
    local patch_dir="$2"
    local label="$3"
    local patch
    local name
    local head
    local -a series=()
    local -a apply_opts=()

    [ -d "$patch_dir" ] || return 0
    [ -d "$source_dir/.git" ] || fail "Source tree was not found for ${label}: $source_dir"

    mapfile -t series < <(find "$patch_dir" -maxdepth 1 -type f -name '*.patch' | sort)
    [ "${#series[@]}" -gt 0 ] || return 0

    head="$(git -C "$source_dir" rev-parse HEAD)"
    echo "Applying ${label} patches at $head"

    for patch in "${series[@]}"; do
        name="$(basename "$patch")"

        case "$label:$name" in
            system/core:0001-libmodprobe-accept-compact-softdeps.patch)
                apply_opts=(--unidiff-zero)
                ;;
            *)
                apply_opts=()
                ;;
        esac

        if ! git -C "$source_dir" apply "${apply_opts[@]}" --numstat "$patch" >/dev/null; then
            fail "Patch syntax validation failed for ${label}: $name"
        fi

        if git -C "$source_dir" apply "${apply_opts[@]}" --reverse --check "$patch" >/dev/null 2>&1; then
            echo "[already applied] ${label}: $name"
            continue
        fi

        git -C "$source_dir" apply "${apply_opts[@]}" --check "$patch" ||
            fail "Patch applicability validation failed for ${label}: $name"
        git -C "$source_dir" apply "${apply_opts[@]}" "$patch"
        echo "[applied] ${label}: $name"
    done
}

apply_external_patch_series "$SYSTEM_CORE_DIR" "$SYSTEM_CORE_PATCH_DIR" "system/core"
apply_external_patch_series "$SYSTEM_UPDATE_ENGINE_DIR" "$SYSTEM_UPDATE_ENGINE_PATCH_DIR" "system/update_engine"
apply_external_patch_series "$SYSTEM_VOLD_DIR" "$SYSTEM_VOLD_PATCH_DIR" "system/vold"
apply_external_patch_series "$SYSTEM_EXTRAS_DIR" "$SYSTEM_EXTRAS_PATCH_DIR" "system/extras"

grep -Fq 'Accept vendor modules.softdep entries that omit whitespace after pre/post.' \
    "$SYSTEM_CORE_DIR/libmodprobe/libmodprobe.cpp" ||
    fail "libmodprobe does not accept compact vendor softdep metadata"

grep -Fq 'errno != EEXIST' "$SYSTEM_VOLD_DIR/KeyStorage.cpp" ||
    fail "vold still logs an existing temporary key directory as an error"

grep -Fq "$FAILED_VAB_SIDELOAD_MARKER" \
    "$SYSTEM_UPDATE_ENGINE_DIR/aosp/cleanup_previous_update_action.cc" ||
    fail "recovery update_engine does not clear a failed Virtual A/B update before sideload"

lpdump_service_lookups="$(grep -F -c 'getService(String16("lpdump_service"), &service_);' \
    "$SYSTEM_EXTRAS_DIR/partition_tools/lpdump_target.cc" || true)"
[ "$lpdump_service_lookups" -eq 2 ] ||
    fail "lpdump does not consistently retry the registered lpdump_service binder endpoint"

if grep -Fq 'getService(String16("lpdump"), &service_);' \
        "$SYSTEM_EXTRAS_DIR/partition_tools/lpdump_target.cc"; then
    fail "lpdump still retries the nonexistent lpdump binder service"
fi

grep -Fq "$LPDUMP_BINDER_LIBRARY" "$RECOVERY_DIR/prebuilt/Android.mk" ||
    fail "recovery does not package libfs_mgr_binder for lpdumpd"

grep -Fq "$LPDUMP_SNAPSHOT_LIBRARY" "$RECOVERY_DIR/prebuilt/Android.mk" ||
    fail "recovery does not package libsnapshot for lpdumpd"

grep -Fq "$LPDUMP_RELINK_DEPENDENCIES" "$RECOVERY_DIR/prebuilt/Android.mk" ||
    fail "recovery does not refresh lpdump binaries during incremental builds"

grep -Fq "$LPDUMP_LIBRARY_RELINK_FIRST_LINE" "$RECOVERY_DIR/prebuilt/Android.mk" &&
    grep -Fq "$LPDUMP_LIBRARY_RELINK_SNAPSHOT_LINE" "$RECOVERY_DIR/prebuilt/Android.mk" ||
    fail "recovery does not refresh lpdump runtime libraries during incremental builds"

python3 - "$RECOVERY_DIR/gui/action.cpp" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

def find_required(needle: str, start: int = 0, desc: str | None = None) -> int:
    pos = text.find(needle, start)
    if pos == -1:
        raise SystemExit(f"ERROR: could not find {desc or needle!r} in {path}")
    return pos

# Keep the Wi-Fi status icon passive: no new GUI action/thread is added. We only
# update the existing GUI variable from the already-running WLAN connect/stop paths.
stop_marker = "// OP15 Wi-Fi status icon disconnect START"
if stop_marker not in text:
    stop_start = find_required("int GUIAction::wlanstop(", desc="wlanstop function")
    stop_if = find_required("\tif (logBox) {", stop_start, "wlanstop logBox block")
    stop_insert = (
        "\t// OP15 Wi-Fi status icon disconnect START\n"
        "\tDataManager::SetValue(\"tw_wifi_connected\", \"0\");\n"
        "\tandroid::base::SetProperty(\"twrp.wifi.connected\", \"0\");\n"
        "\tandroid::base::SetProperty(\"twrp.wifi.ssid\", \"\");\n"
        "\tandroid::base::SetProperty(\"twrp.wifi.ip\", \"\");\n"
        "\t// OP15 Wi-Fi status icon disconnect END\n"
    )
    text = text[:stop_if] + stop_insert + text[stop_if:]

connect_start = find_required("int GUIAction::wlanconnect(", desc="wlanconnect function")
connect_start_marker = "// OP15 Wi-Fi status icon connect-start START"
if connect_start_marker not in text:
    selected_anchor = find_required("    // 读取选中的 WLAN\n", connect_start, "wlanconnect selected WLAN anchor")
    connect_start_insert = (
        "    // OP15 Wi-Fi status icon connect-start START\n"
        "    DataManager::SetValue(\"tw_wifi_connected\", \"0\");\n"
        "    android::base::SetProperty(\"twrp.wifi.connected\", \"0\");\n"
        "    // OP15 Wi-Fi status icon connect-start END\n\n"
    )
    text = text[:selected_anchor] + connect_start_insert + text[selected_anchor:]

connected_marker = "// OP15 Wi-Fi status icon connected START"
if connected_marker not in text:
    # This anchor is intentionally after patch 0004's DNS-ready verification and
    # before the success logging. By this point association, DHCP, and DNS setup
    # have all succeeded.
    gateway_anchor = find_required("    // 获取网关\n", connect_start, "wlanconnect gateway anchor")
    connected_insert = (
        "    // OP15 Wi-Fi status icon connected START\n"
        "    DataManager::SetValue(\"tw_wifi_connected\", \"1\");\n"
        "    android::base::SetProperty(\"twrp.wifi.connected\", \"1\");\n"
        "    android::base::SetProperty(\"twrp.wifi.ssid\", selectedWlan.c_str());\n"
        "    android::base::SetProperty(\"twrp.wifi.ip\", ip_address.c_str());\n"
        "    // OP15 Wi-Fi status icon connected END\n\n"
    )
    text = text[:gateway_anchor] + connected_insert + text[gateway_anchor:]

path.write_text(text, encoding="utf-8")
PY

echo "[patched] Wi-Fi status icon state wiring in gui/action.cpp"

mkdir -p "$(dirname "$WIFI_STATUS_ICON")"
base64 -d "$WIFI_STATUS_ICON_B64" > "$WIFI_STATUS_ICON"
chmod 0644 "$WIFI_STATUS_ICON"
echo "[installed] portrait_hdpi Wi-Fi status icon: $WIFI_STATUS_ICON"

python3 "$DEVICE_DIR/tools/patch_twrp_magisk_theme.py" \
    "$RECOVERY_DIR/gui/theme/common/portrait.xml"

sed -i 's/[[:space:]]\+$//' "$RECOVERY_DIR/gui/theme/common/portrait.xml"

git -C "$RECOVERY_DIR" diff --check

PIGZ_TEST_COUNT="$(grep -F -c "$PIGZ_TEST_CALL" "$RECOVERY_DIR/twrpTar.cpp" 2>/dev/null || true)"
if [ "$PIGZ_TEST_COUNT" -ne 2 ]; then
    fail "Expected two parallel pigz -9 backup paths in twrpTar.cpp; found $PIGZ_TEST_COUNT"
fi

if grep -F -q 'execlp("pigz", "pigz", "-", NULL)' "$RECOVERY_DIR/twrpTar.cpp"; then
    fail "A default-level pigz backup path remains in twrpTar.cpp"
fi

ZSTD_COMPRESS_COUNT="$(grep -F -c "$ZSTD_COMPRESS_CALL" "$RECOVERY_DIR/twrpTar.cpp" 2>/dev/null || true)"
if [ "$ZSTD_COMPRESS_COUNT" -ne 2 ]; then
    fail "Expected two zstd compression paths in twrpTar.cpp; found $ZSTD_COMPRESS_COUNT"
fi

ZSTD_DECOMPRESS_COUNT="$(grep -F -c "$ZSTD_DECOMPRESS_CALL" "$RECOVERY_DIR/twrpTar.cpp" 2>/dev/null || true)"
if [ "$ZSTD_DECOMPRESS_COUNT" -ne 2 ]; then
    fail "Expected two zstd decompression paths in twrpTar.cpp; found $ZSTD_DECOMPRESS_COUNT"
fi

grep -Fq '#define TW_BACKUP_COMPRESSION_VAR   "tw_backup_compression"' "$RECOVERY_DIR/variables.h" ||
    fail "TWRP does not persist the selected backup compression type"

grep -Fq 'return ZSTD_COMPRESSED;' "$RECOVERY_DIR/twrp-functions.cpp" ||
    fail "TWRP does not detect zstd backup frames"

grep -Fq 'return 4; // Zstd compressed' "$RECOVERY_DIR/twrp-functions.cpp" ||
    fail "TWRP does not detect encrypted zstd backup frames"

grep -Fq 'tw_backup_compression=1' "$RECOVERY_DIR/gui/theme/common/portrait.xml" ||
    fail "portrait backup options do not expose the zstd compression choice"

grep -Fq 'tw_backup_compression=1' "$RECOVERY_DIR/gui/theme/common/landscape.xml" ||
    fail "landscape backup options do not expose the zstd compression choice"

for resource in backup_compression_type backup_compression_pigz backup_compression_zstd; do
    grep -Fq "<string name=\"$resource\"" "$RECOVERY_DIR/gui/theme/common/languages/en.xml" ||
        fail "English language resource '$resource' is missing for backup compression"
done

grep -Fq 'TW_INCLUDE_ZSTD               := true' "$DEVICE_DIR/BoardConfig.mk" ||
    fail "recovery is not configured to package the zstd executable"

if grep -i -q 'orangefox' "$RECOVERY_DIR/gui/fileselector.cpp"; then
    fail "OrangeFox filename compatibility remains in gui/fileselector.cpp"
fi

DNS_PUBLISH_COUNT="$(grep -F -c "$DNS_PUBLISH_CALL" "$RECOVERY_DIR/gui/action.cpp" 2>/dev/null || true)"
if [ "$DNS_PUBLISH_COUNT" -ne 2 ]; then
    fail "Expected two root DNS publisher calls in gui/action.cpp; found $DNS_PUBLISH_COUNT"
fi

if ! grep -F -q 'DNS resolver setup failed' "$RECOVERY_DIR/gui/action.cpp"; then
    fail "Wi-Fi connection path does not verify DNS resolver setup"
fi

if ! grep -F -q "$NANDSWAP_EXCLUSION" "$RECOVERY_DIR/partition.cpp"; then
    fail "FBE backup path does not directly exclude /data/nandswap"
fi

if ! grep -F -q 'OP15 Wi-Fi status icon connected START' "$RECOVERY_DIR/gui/action.cpp"; then
    fail "Wi-Fi connection path does not update tw_wifi_connected"
fi

if ! grep -F -q 'gui_parse_text("{@restore_hdr}")' "$RECOVERY_DIR/openrecoveryscript.cpp"; then
    fail "OpenRecoveryScript restore action does not use the translated restore header"
fi

if grep -F -q 'gui_parse_text("{@restore}")' "$RECOVERY_DIR/openrecoveryscript.cpp"; then
    fail "OpenRecoveryScript restore action still references the missing restore string"
fi

if ! grep -F -q 'restore <backupname> [SDCRBAEM]' "$RECOVERY_DIR/orscmd/orscmd.cpp"; then
    fail "TWRP CLI restore usage does not document backup-name-first argument order"
fi

if ! grep -F -q 'DataManager::SetValue("tw_wifi_connected", "1")' "$RECOVERY_DIR/gui/action.cpp"; then
    fail "Wi-Fi connection path does not mark the icon connected"
fi

for advanced_item in \
    '/system/bin/twrp-flash-magisk init_boot' \
    '/system/bin/twrp-ftp-menu' \
    '/system/bin/twrp-avb-tool'; do
    grep -F -q "$advanced_item" "$RECOVERY_DIR/gui/theme/common/portrait.xml" ||
        fail "Advanced theme is missing the required helper entry: $advanced_item"
done

if ! grep -F -q '<image name="wifi_status" filename="wifi_status" retainaspect="1"/>' \
        "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml" ||
    ! grep -F -q '<image resource="wifi_status"/>' \
        "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml"; then
    fail "portrait_hdpi theme does not declare and draw the Wi-Fi status icon"
fi

[ -s "$WIFI_STATUS_ICON" ] || fail "Wi-Fi status icon asset was not installed"

echo "[verified] helper module identities and runtime paths are unversioned"
echo "[verified] backup compression offers parallel pigz -9 and multithreaded zstd -11"
echo "[verified] Advanced theme includes bundled Magisk, FTP, and AVB helper menus"
echo "[verified] OrangeFox filename compatibility is removed from the file selector"
echo "[verified] Wi-Fi connection and test paths publish DNS from the root recovery process"
echo "[verified] FBE backups exclude regeneratable /data/nandswap data"
echo "[verified] Wi-Fi status icon image resource is wired into the portrait_hdpi status bar"
echo "[verified] OpenRecoveryScript restore uses an available translated string and correct CLI argument order"
echo "[verified] recovery sideload clears a failed Virtual A/B update before a replacement OTA"

echo
echo "Recovery patches are ready for the next build."
echo "Modified recovery source files:"
git -C "$RECOVERY_DIR" status --short
