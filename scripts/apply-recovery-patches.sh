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
HELPER_VALIDATOR="$SCRIPT_DIR/validate-helper-modules.sh"
EXPECTED_BASE="6bd8134ec8ff4cb29eb25797cbb20796f8455204"
PIGZ_MAX_CALL='execlp("pigz", "pigz", "-9", "-", NULL)'
DNS_PUBLISH_CALL='/system/bin/twrp-dns-publish wlan0 2>&1'
NANDSWAP_EXCLUSION='ExcludeAll(Mount_Point + "/nandswap")'

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -f "$HELPER_VALIDATOR" ] || fail "Helper module validator was not found: $HELPER_VALIDATOR"
bash "$HELPER_VALIDATOR"

[ -d "$RECOVERY_DIR/.git" ] ||
    fail "TWRP recovery source was not found at $RECOVERY_DIR"

command -v git >/dev/null 2>&1 || fail "git is not installed"

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

echo "[verified] helper module identities and runtime paths are unversioned"
echo "[verified] pigz -9 is active for compressed and compressed-encrypted backups"
echo "[verified] OrangeFox filename compatibility is removed from the file selector"
echo "[verified] Wi-Fi connection and test paths publish DNS from the root recovery process"
echo "[verified] FBE backups exclude regeneratable /data/nandswap data"

echo
echo "Recovery patches are ready for the next build."
echo "Modified recovery source files:"
git -C "$RECOVERY_DIR" status --short
