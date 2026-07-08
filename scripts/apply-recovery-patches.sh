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
THEME_ASSET_DIR="$DEVICE_DIR/assets/twrp-theme"
HELPER_VALIDATOR="$SCRIPT_DIR/validate-helper-modules.sh"
EXPECTED_BASE="6bd8134ec8ff4cb29eb25797cbb20796f8455204"
PIGZ_MAX_CALL='execlp("pigz", "pigz", "-9", "-", NULL)'
DNS_PUBLISH_CALL='/system/bin/twrp-dns-publish wlan0 2>&1'
NANDSWAP_EXCLUSION='ExcludeAll(Mount_Point + "/nandswap")'
WIFI_ICON_MARKER='OP15 Wi-Fi status icon START'
WIFI_STATUS_ICON="$RECOVERY_DIR/gui/theme/portrait_hdpi/images/wifi_status.png"
WIFI_STATUS_ICON_B64="$THEME_ASSET_DIR/wifi_status.png.b64"

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

    if ! git apply --numstat "$patch" >/dev/null; then
        fail "Patch syntax validation failed: $name"
    fi

    case "$name" in
        0001-wifi-use-returned-network-id.patch)
            if grep -F -q 'Supplicant network ID' "$RECOVERY_DIR/gui/action.cpp"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
        0006-wifi-show-connected-status-icon.patch)
            if grep -F -q "$WIFI_ICON_MARKER" "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml" &&
                grep -F -q '<image name="wifi_status" filename="wifi_status" retainaspect="1"/>' \
                    "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml"; then
                echo "[already applied] $name"
                continue
            fi
            ;;
    esac

    if git -C "$RECOVERY_DIR" apply --reverse --check "$patch" >/dev/null 2>&1; then
        echo "[already applied] $name"
        continue
    fi

    if ! git -C "$RECOVERY_DIR" apply --check "$patch"; then
        echo >&2
        echo "Patch applicability validation failed: $name" >&2
        echo "The recovery checkout may have moved beyond the source revision this patch targets." >&2
        echo "Current HEAD:   $CURRENT_HEAD" >&2
        echo "Reference HEAD: $EXPECTED_BASE" >&2
        exit 1
    fi

    git -C "$RECOVERY_DIR" apply "$patch"
    echo "[applied] $name"
done

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

sed -i 's/[[:space:]]\+$//' "$RECOVERY_DIR/gui/theme/common/portrait.xml"

git -C "$RECOVERY_DIR" diff --check

PIGZ_MAX_COUNT="$(grep -F -c "$PIGZ_MAX_CALL" "$RECOVERY_DIR/twrpTar.cpp" 2>/dev/null || true)"
if [ "$PIGZ_MAX_COUNT" -ne 2 ]; then
    fail "Expected two pigz -9 backup paths in twrpTar.cpp; found $PIGZ_MAX_COUNT"
fi

if grep -F -q 'execlp("pigz", "pigz", "-", NULL)' "$RECOVERY_DIR/twrpTar.cpp"; then
    fail "A default-level pigz backup path remains in twrpTar.cpp"
fi

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

if ! grep -F -q 'DataManager::SetValue("tw_wifi_connected", "1")' "$RECOVERY_DIR/gui/action.cpp"; then
    fail "Wi-Fi connection path does not mark the icon connected"
fi

if ! grep -F -q "$WIFI_ICON_MARKER" "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml"; then
    fail "portrait_hdpi theme does not draw the Wi-Fi status icon"
fi

if ! grep -F -q '<image name="wifi_status" filename="wifi_status" retainaspect="1"/>' \
    "$RECOVERY_DIR/gui/theme/portrait_hdpi/ui.xml"; then
    fail "portrait_hdpi theme does not declare the Wi-Fi status icon resource"
fi

[ -s "$WIFI_STATUS_ICON" ] || fail "Wi-Fi status icon asset was not installed"

echo "[verified] helper module identities and runtime paths are unversioned"
echo "[verified] pigz -9 is active for compressed and compressed-encrypted backups"
echo "[verified] OrangeFox filename compatibility is removed from the file selector"
echo "[verified] Wi-Fi connection and test paths publish DNS from the root recovery process"
echo "[verified] FBE backups exclude regeneratable /data/nandswap data"
echo "[verified] Wi-Fi status icon image resource is wired into the portrait_hdpi status bar"

echo
echo "Recovery patches are ready for the next build."
echo "Modified recovery source files:"
git -C "$RECOVERY_DIR" status --short
