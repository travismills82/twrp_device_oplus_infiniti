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
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is not installed"
[ "$(wc -c < "$RECOVERY_IMAGE" | tr -d ' ')" = 104857600 ] || \
    fail "Expected the complete 100 MiB Infiniti recovery image"

# Resolve the output before entering the temporary package directory. GitHub
# Actions supplies a workspace-relative artifact path.
OUTPUT_DIR="$(dirname "$OUTPUT_ZIP")"
OUTPUT_NAME="$(basename "$OUTPUT_ZIP")"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
OUTPUT_ZIP="$OUTPUT_DIR/$OUTPUT_NAME"

# Do not scan the compressed recovery image as arbitrary compressed bytes can
# coincidentally match a branding token. GitHub Actions scans the uncompressed
# recovery staging tree before this builder is invoked and reports exact files
# for any genuine filename, text, or printable binary-string match.

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

META_DIR="$WORK_DIR/META-INF/com/google/android"
mkdir -p "$META_DIR"

cat > "$META_DIR/update-binary" <<'INSTALLER'
#!/sbin/sh

OUTFD="$2"
ZIPFILE="$3"
TMPDIR=""
IMAGE=""
umask 077
trap '[ -z "$TMPDIR" ] || rm -rf "$TMPDIR"' EXIT
trap 'exit 1' HUP INT TERM

ui_print() {
    echo "ui_print $*" > "/proc/self/fd/$OUTFD"
    echo "ui_print" > "/proc/self/fd/$OUTFD"
}

abort_install() {
    ui_print ""
    ui_print "ERROR: $*"
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

    partition_size="$(blockdev --getsize64 "$partition" 2>/dev/null)" || \
        abort_install "Cannot read the size of $partition"
    [ "$partition_size" = "$image_size" ] || \
        abort_install "Unexpected partition size for $partition"
}

flash_partition() {
    label="$1"
    partition="$2"

    ui_print "Flashing $label..."
    dd if="$IMAGE" of="$partition" bs=4M 2>/dev/null || \
        abort_install "Failed to write $label"
    sync
    written_sha="$(sha256sum "$partition")" || abort_install "Cannot verify $label"
    written_sha="${written_sha%% *}"
    [ "$written_sha" = "$IMAGE_SHA256" ] || abort_install "Readback mismatch for $label"
    ui_print "Verified $label"
}

command -v getprop >/dev/null 2>&1 || abort_install "Recovery properties are unavailable"
[ "$(id -u)" = 0 ] || abort_install "Run this installer from recovery"
[ -n "$(getprop ro.twrp.version)" ] || abort_install "Run this installer from TWRP recovery"
# Bootloader project IDs match libinit_oplus_infiniti.cpp; product names can be spoofed.
case "$(getprop ro.boot.prjname)" in
    24831|24863) ;;
    *) abort_install "This ZIP is only for OnePlus 15 (infiniti)" ;;
esac
command -v blockdev >/dev/null 2>&1 || abort_install "blockdev is unavailable"
command -v sha256sum >/dev/null 2>&1 || abort_install "sha256sum is unavailable"

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

TMPDIR="$(mktemp -d /tmp/twrp-dual-slot-installer.XXXXXX)" || abort_install "Unable to create temporary directory"
IMAGE="$TMPDIR/recovery.img"
$UNZIP_BIN -o "$ZIPFILE" recovery.img recovery.img.sha256 -d "$TMPDIR" >/dev/null 2>&1 || \
    abort_install "recovery.img is missing or could not be extracted"

[ -s "$IMAGE" ] || abort_install "Extracted recovery.img is empty"
IMAGE_SHA256="$(cat "$TMPDIR/recovery.img.sha256" 2>/dev/null)"
case "$IMAGE_SHA256" in
    ''|*[!0-9a-f]*) abort_install "Invalid recovery image checksum" ;;
esac
[ "${#IMAGE_SHA256}" = 64 ] || abort_install "Invalid recovery image checksum length"
actual_sha="$(sha256sum "$IMAGE")" || abort_install "Cannot verify recovery.img"
[ "${actual_sha%% *}" = "$IMAGE_SHA256" ] || abort_install "Recovery image checksum mismatch"

RECOVERY_A="$(find_partition recovery_a || true)"
RECOVERY_B="$(find_partition recovery_b || true)"

[ -n "$RECOVERY_A" ] || abort_install "recovery_a partition was not found"
[ -n "$RECOVERY_B" ] || abort_install "recovery_b partition was not found"

IMAGE_SIZE="$(wc -c < "$IMAGE" | tr -d ' ')"
case "$IMAGE_SIZE" in
    ''|*[!0-9]*) abort_install "Unable to determine recovery.img size" ;;
esac
[ "$IMAGE_SIZE" = 104857600 ] || abort_install "Unexpected recovery image size"
[ "$(readlink -f "$RECOVERY_A")" != "$(readlink -f "$RECOVERY_B")" ] || \
    abort_install "Both recovery slots resolve to the same partition"

ui_print "Image size: $IMAGE_SIZE bytes"
ui_print "Slot A: $RECOVERY_A"
ui_print "Slot B: $RECOVERY_B"
ui_print ""

check_partition_size "$RECOVERY_A" "$IMAGE_SIZE"
check_partition_size "$RECOVERY_B" "$IMAGE_SIZE"

# Optional command-line preflight; TWRP's normal three-argument invocation flashes.
case "${4:-}" in
    --dry-run)
        ui_print "Preflight passed. No partitions were written."
        exit 0
        ;;
    '') ;;
    *) abort_install "Unknown installer option" ;;
esac

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

Install through TWRP on OnePlus 15 only (boot project 24831 or 24863).
The installer checks the image checksum and both partition sizes before writing,
then verifies each complete partition against the packaged image checksum.
EOF

cp "$RECOVERY_IMAGE" "$WORK_DIR/recovery.img"
IMAGE_SHA256="$(sha256sum "$WORK_DIR/recovery.img")"
printf '%s\n' "${IMAGE_SHA256%% *}" > "$WORK_DIR/recovery.img.sha256"

# Scan the generated installer text. The recovery ramdisk itself was already
# checked in its uncompressed staging tree by the workflow.
if LC_ALL=C grep -R -I -i -E -q 'OrangeFox|Orange Fox|OFRP' "$WORK_DIR/META-INF" "$WORK_DIR/INSTALL.txt"; then
    fail "Generated installer contains OrangeFox/OFRP branding"
fi

rm -f "$OUTPUT_ZIP"
(
    cd "$WORK_DIR"
    zip -q -r -9 "$OUTPUT_ZIP" META-INF INSTALL.txt recovery.img recovery.img.sha256
)

# Verify the package structure and installer behavior markers.
unzip -t "$OUTPUT_ZIP" >/dev/null
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/update-binary'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/updater-script'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'META-INF/com/google/android/twrp-version'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'recovery.img'
unzip -Z1 "$OUTPUT_ZIP" | grep -qx 'recovery.img.sha256'
PACKED_SHA256="$(unzip -p "$OUTPUT_ZIP" recovery.img | sha256sum)"
[ "${PACKED_SHA256%% *}" = "${IMAGE_SHA256%% *}" ] || fail "ZIP recovery payload differs from the input image"
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'find_partition recovery_a'
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'find_partition recovery_b'
unzip -p "$OUTPUT_ZIP" META-INF/com/google/android/update-binary | grep -q 'Successfully installed'

if unzip -Z1 "$OUTPUT_ZIP" | grep -i -E -q 'OrangeFox|Orange Fox|OFRP'; then
    fail "ZIP filenames contain OrangeFox/OFRP branding"
fi

printf 'Created %s\n' "$OUTPUT_ZIP"
printf 'Installer version: %s for %s\n' "$TWRP_VERSION" "$DEVICE_NAME"
unzip -l "$OUTPUT_ZIP"
