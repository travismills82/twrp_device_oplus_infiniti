#!/usr/bin/env bash
# Build a clean, recovery-flashable TWRP package for the OnePlus 15.
#
# Usage:
#   build-twrp-installer.sh RECOVERY_IMAGE OUTPUT_ZIP TWRP_VERSION DEVICE_NAME
#
# The generated update-binary writes recovery.img to both recovery_a and
# recovery_b. The package is created from scratch and contains no inherited
# recovery-project branding or installer payloads.

set -euo pipefail

RECOVERY_IMAGE="${1:-}"
OUTPUT_ZIP="${2:-}"
TWRP_VERSION="${3:-TWRP 3.7.1-16}"
DEVICE_NAME="${4:-OnePlus 15 (infiniti)}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

[ -f "$RECOVERY_IMAGE" ] || fail "Recovery image not found: $RECOVERY_IMAGE"
[ -n "$OUTPUT_ZIP" ] || fail "Output ZIP path was not supplied"
command -v zip >/dev/null 2>&1 || fail "zip is not installed"
command -v unzip >/dev/null 2>&1 || fail "unzip is not installed"

# Reject images that still contain branding from the package this installer
# replaces. This check scans the actual recovery image, not only ZIP metadata.
if LC_ALL=C grep -a -i -E -q 'OrangeFox|OFRP' "$RECOVERY_IMAGE"; then
    fail "Recovery image contains OrangeFox/OFRP branding"
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

META_DIR="$WORK_DIR/META-INF/com/google/android"
mkdir -p "$META_DIR"

cat > "$META_DIR/update-binary" <<'INSTALLER'
#!/sbin/sh

OUTFD="$2"
ZIPFILE="$3"
TMPDIR="/tmp/twrp-dual-slot-installer.$$"
IMAGE="$TMPDIR/recovery.img"

ui_print() {
    echo "ui_print $*" > "/proc/self/fd/$OUTFD"
    echo "ui_print" > "/proc/self/fd/$OUTFD"
}

abort_install() {
    ui_print ""
    ui_print "ERROR: $*"
    rm -rf "$TMPDIR"
    exit 1
}

find_partition() {
    partition_name="$1"

    for candidate in \
        "/dev/block/by-name/$partition_name" \
        "/dev/block/bootdevice/by-name/$partition_name"; do
        if [ -b "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    for candidate in \
        /dev/block/platform/*/by-name/"$partition_name" \
        /dev/block/platform/*/*/by-name/"$partition_name"; do
        if [ -b "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

check_partition_size() {
    partition="$1"
    image_size="$2"

    if command -v blockdev >/dev/null 2>&1; then
        partition_size="$(blockdev --getsize64 "$partition" 2>/dev/null || true)"
        case "$partition_size" in
            ''|*[!0-9]*) return 0 ;;
        esac

        if [ "$image_size" -gt "$partition_size" ]; then
            abort_install "recovery.img is larger than $partition"
        fi
    fi
}

flash_partition() {
    label="$1"
    partition="$2"

    ui_print "Flashing $label..."
    dd if="$IMAGE" of="$partition" bs=4M 2>/dev/null || \
        abort_install "Failed to write $label"
    sync
}

UNZIP_BIN="$(command -v unzip 2>/dev/null || true)"
[ -n "$UNZIP_BIN" ] || abort_install "unzip is not available in recovery"

VERSION="$($UNZIP_BIN -p "$ZIPFILE" META-INF/com/google/android/twrp-version 2>/dev/null | tr -d '\r\n')"
[ -n "$VERSION" ] || VERSION="TWRP recovery"

ui_print ""
ui_print "========================================"
ui_print "  $VERSION"
ui_print "  Dual-slot recovery installer"
ui_print "========================================"
ui_print "Package: $(basename "$ZIPFILE")"
ui_print "Target: OnePlus 15 (infiniti)"
ui_print ""

mkdir -p "$TMPDIR" || abort_install "Unable to create temporary directory"
$UNZIP_BIN -o "$ZIPFILE" recovery.img -d "$TMPDIR" >/dev/null 2>&1 || \
    abort_install "recovery.img is missing or could not be extracted"

[ -s "$IMAGE" ] || abort_install "Extracted recovery.img is empty"

RECOVERY_A="$(find_partition recovery_a || true)"
RECOVERY_B="$(find_partition recovery_b || true)"

[ -n "$RECOVERY_A" ] || abort_install "recovery_a partition was not found"
[ -n "$RECOVERY_B" ] || abort_install "recovery_b partition was not found"

IMAGE_SIZE="$(wc -c < "$IMAGE" | tr -d ' ')"
case "$IMAGE_SIZE" in
    ''|*[!0-9]*) abort_install "Unable to determine recovery.img size" ;;
esac

ui_print "Image size: $IMAGE_SIZE bytes"
ui_print "Slot A: $RECOVERY_A"
ui_print "Slot B: $RECOVERY_B"
ui_print ""

check_partition_size "$RECOVERY_A" "$IMAGE_SIZE"
check_partition_size "$RECOVERY_B" "$IMAGE_SIZE"

flash_partition recovery_a "$RECOVERY_A"
flash_partition recovery_b "$RECOVERY_B"

rm -rf "$TMPDIR"

ui_print ""
ui_print "Successfully installed $VERSION"
ui_print "Flashed recovery_a and recovery_b"
ui_print "No active slot was changed."
ui_print ""
exit 0
INSTALLER

chmod 0755 "$META_DIR/update-binary"

cat > "$META_DIR/updater-script" <<'UPDATER'
# TWRP dual-slot recovery installer
# Installation is performed by META-INF/com/google/android/update-binary.
UPDATER

printf '%s for %s\n' "$TWRP_VERSION" "$DEVICE_NAME" > "$META_DIR/twrp-version"

cat > "$WORK_DIR/INSTALL.txt" <<EOF
$TWRP_VERSION Dual-Slot Recovery Installer

Device: $DEVICE_NAME

This package installs the included recovery.img to both recovery_a and
recovery_b. It does not change the active boot slot.
EOF

cp "$RECOVERY_IMAGE" "$WORK_DIR/recovery.img"

# Scan every generated text file before packaging. The image was scanned above.
if LC_ALL=C grep -R -a -i -E -q 'OrangeFox|OFRP' "$WORK_DIR/META-INF" "$WORK_DIR/INSTALL.txt"; then
    fail "Generated installer contains OrangeFox/OFRP branding"
fi

mkdir -p "$(dirname "$OUTPUT_ZIP")"
rm -f "$OUTPUT_ZIP"
(
    cd "$WORK_DIR"
    zip -q -r -9 "$OUTPUT_ZIP" META-INF INSTALL.txt recovery.img
)

# Verify the package structure and installer behavior markers.
unzip -t "$OUTPUT_ZIP" >/dev/null
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/update-binary'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/updater-script'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/twrp-version'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'recovery.img'
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'find_partition recovery_a'
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'find_partition recovery_b'
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'Successfully installed'

if unzip -Z1 "$OUTPUT_ZIP" | grep -i -E -q 'OrangeFox|OFRP'; then
    fail "ZIP filenames contain OrangeFox/OFRP branding"
fi

printf 'Created %s\n' "$OUTPUT_ZIP"
printf 'Installer version: %s for %s\n' "$TWRP_VERSION" "$DEVICE_NAME"
unzip -l "$OUTPUT_ZIP"
