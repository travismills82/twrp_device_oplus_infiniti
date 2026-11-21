#!/usr/bin/env bash
# Host-only validation. Never calls ADB/fastboot or changes a phone.
set -euo pipefail
DEVICE="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${1:-$(CDPATH= cd -- "$DEVICE/../../.." && pwd)}"
cd "$ROOT"
python3 -B "$DEVICE/scripts/test-ab-ota-recovery-safety.py" "$ROOT/bootable/recovery"
python3 -B "$DEVICE/scripts/test-sideload-usb.py"
python3 -B "$DEVICE/scripts/test-decrypt-readiness.py"
python3 -B "$DEVICE/scripts/test-wifi-runtime-firmware.py"
python3 -B "$DEVICE/scripts/test-native-backup.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-gpu-renderer.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-cellular-status.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-wifi-profiles.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-charging.py"
python3 -B "$DEVICE/scripts/test-oxygenos-dashboard.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-modern-wifi.py" "$ROOT"
python3 -B "$DEVICE/scripts/test-truetype-lifetime.py" "$ROOT"
FIXTURE="$(mktemp -d /tmp/twrp-oxygenos-validation.XXXXXX)"
trap 'rm -rf -- "$FIXTURE"' EXIT
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-native-backup-safety.cpp" -o "$FIXTURE/test-native-backup"
"$FIXTURE/test-native-backup" "$FIXTURE"
python3 -B "$DEVICE/scripts/test-smb-browser.py" "$ROOT"
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-smb-browser.cpp" -o "$FIXTURE/test-smb-browser"
"$FIXTURE/test-smb-browser"
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-network-tile-sessions.cpp" -o "$FIXTURE/test-network-tile-sessions"
"$FIXTURE/test-network-tile-sessions" "$FIXTURE"
sh -n "$DEVICE/recovery/root/system/bin/twrp-curl"
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-input-frame-pacer.cpp" -o "$FIXTURE/test-input-frame-pacer"
"$FIXTURE/test-input-frame-pacer"
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-wifi-traffic.cpp" -o "$FIXTURE/test-wifi-traffic"
"$FIXTURE/test-wifi-traffic"
g++ -std=c++17 -Wall -Wextra -Werror -I "$ROOT/bootable/recovery" \
    "$DEVICE/scripts/test-double-tap-wake.cpp" -o "$FIXTURE/test-double-tap-wake"
"$FIXTURE/test-double-tap-wake"
xmllint --noout "$ROOT/bootable/recovery/gui/theme/portrait_hdpi/ui.xml" \
    "$ROOT/bootable/recovery/gui/theme/common/portrait.xml"
git -C "$ROOT/bootable/recovery" diff --check
git -C "$DEVICE" diff --check
if [ -n "${2:-}" ]; then
    python3 -B "$DEVICE/tools/verify_oxygenos_image.py" "$2" --root "$ROOT"
    python3 -B "$DEVICE/scripts/verify-gpu-image.py" "$2" --root "$ROOT"
fi
echo 'OxygenOS UI and recovery non-regression validation PASS (host/source; not physical qualification)'
