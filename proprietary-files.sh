#!/usr/bin/env bash
#
# Refresh every existing proprietary .ko, .so, and .bin file in this device
# tree, plus the recovery Wi-Fi and firmware payloads, from a connected rooted
# OnePlus 15.
#
# Supported OnePlus 15 identifiers:
#   codename: infiniti
#   models:   CPH2747, CPH2745, CPH2749, PLK110
#
# This revision is deliberately verbose. It prints every phase immediately,
# writes a timestamped debug log, uses non-interactive root commands, and
# reports the exact line/command if anything fails.
#

set -Eeuo pipefail

TREE="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_VERSION="5.1-all-ko-so-bin"
EXPECTED_DEVICE="infiniti"
SUPPORTED_MODELS=(CPH2747 CPH2745 CPH2749 PLK110)

SERIAL=""
DRY_RUN=0
BACKUP=1
ALLOW_MISSING=0
FORCE_DEVICE=0
DEBUG=0
TRACE=0
DIAGNOSE_ONLY=0
LIST_LOCAL=0

ADB_TIMEOUT=15
ROOT_TIMEOUT=25
REMOTE_TIMEOUT=15
SEARCH_TIMEOUT=12
PULL_TIMEOUT=180

STARTED_AT="$(date +%Y%m%d-%H%M%S)"
EARLY_LOG="${TMPDIR:-/tmp}/proprietary-files-${STARTED_AT}.log"
LOGFILE="$EARLY_LOG"

usage() {
    cat <<'USAGE'
Usage: ./proprietary-files.sh [options]

Options:
  --version             Print the script version and exit.
  --serial SERIAL       Select a specific adb device.
  --dry-run             Pull and compare files without modifying the tree.
  --list-local          List repository files selected for refresh; then exit.
  --no-backup           Do not preserve replaced files under out/.
  --allow-missing       Update resolved files even if some are unavailable.
  --force-device        Skip the OnePlus 15 codename/model identity check.
  --diagnose-only       Test adb, root, properties, and remote commands; then exit.
  --debug               Print each remote operation and its result.
  --trace               Enable bash xtrace with source line numbers.
  --adb-timeout SEC     Timeout for adb availability checks (default: 15).
  --root-timeout SEC    Timeout while requesting root (default: 25).
  --remote-timeout SEC  Timeout for normal remote commands (default: 15).
  --search-timeout SEC  Timeout for each fallback directory search (default: 12).
  --pull-timeout SEC    Timeout for pulling one file (default: 180).
  -h, --help            Show this help.

Requirements:
  - Keep this script in the device-tree root.
  - Boot the phone into Android and enable USB debugging.
  - Unlock the phone screen.
  - Grant adb shell root access in Magisk/KernelSU when prompted.
USAGE
}

timestamp() {
    date '+%H:%M:%S'
}

log() {
    printf '[%s] [proprietary-files] %s\n' "$(timestamp)" "$*" >&2
}

warn() {
    printf '[%s] [proprietary-files] WARNING: %s\n' "$(timestamp)" "$*" >&2
}

debug() {
    [ "$DEBUG" -eq 1 ] || return 0
    printf '[%s] [proprietary-files] DEBUG: %s\n' "$(timestamp)" "$*" >&2
}

fail() {
    printf '[%s] [proprietary-files] ERROR: %s\n' "$(timestamp)" "$*" >&2
    exit 1
}

on_error() {
    local rc="$1"
    local line="$2"
    local command="$3"
    printf '\n[%s] [proprietary-files] FAILED rc=%s line=%s\n' \
        "$(timestamp)" "$rc" "$line" >&2
    printf '[%s] [proprietary-files] command: %s\n' \
        "$(timestamp)" "$command" >&2
    printf '[%s] [proprietary-files] log: %s\n' \
        "$(timestamp)" "$LOGFILE" >&2
    exit "$rc"
}

trap 'on_error "$?" "$LINENO" "$BASH_COMMAND"' ERR

is_positive_integer() {
    case "$1" in
        ''|*[!0-9]*|0) return 1 ;;
        *) return 0 ;;
    esac
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --version)
            echo "proprietary-files.sh $SCRIPT_VERSION"
            exit 0
            ;;
        --serial)
            [ "$#" -ge 2 ] || fail "--serial requires a value"
            SERIAL="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --list-local)
            LIST_LOCAL=1
            shift
            ;;
        --no-backup)
            BACKUP=0
            shift
            ;;
        --allow-missing)
            ALLOW_MISSING=1
            shift
            ;;
        --force-device)
            FORCE_DEVICE=1
            shift
            ;;
        --diagnose-only)
            DIAGNOSE_ONLY=1
            shift
            ;;
        --debug)
            DEBUG=1
            shift
            ;;
        --trace)
            TRACE=1
            shift
            ;;
        --adb-timeout|--root-timeout|--remote-timeout|--search-timeout|--pull-timeout)
            [ "$#" -ge 2 ] || fail "$1 requires a value"
            is_positive_integer "$2" || fail "invalid timeout value: $2"
            case "$1" in
                --adb-timeout) ADB_TIMEOUT="$2" ;;
                --root-timeout) ROOT_TIMEOUT="$2" ;;
                --remote-timeout) REMOTE_TIMEOUT="$2" ;;
                --search-timeout) SEARCH_TIMEOUT="$2" ;;
                --pull-timeout) PULL_TIMEOUT="$2" ;;
            esac
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
done

# Start logging before any adb or root operation.
exec > >(tee -a "$EARLY_LOG") 2>&1

log "starting version=$SCRIPT_VERSION"
log "early log: $EARLY_LOG"
log "script: ${BASH_SOURCE[0]}"
log "working tree: $TREE"

if [ "$TRACE" -eq 1 ]; then
    PS4='+ [${BASH_SOURCE##*/}:${LINENO}] '
    set -x
fi

[ -f "$TREE/BoardConfig.mk" ] && [ -f "$TREE/device.mk" ] ||
    fail "script must be located in the device-tree root"

mkdir -p "$TREE/out"
LOGFILE="$TREE/out/proprietary-files-${STARTED_AT}.log"
cp "$EARLY_LOG" "$LOGFILE" 2>/dev/null || true

# Mirror subsequent output into both the persistent and early logs.
exec > >(tee -a "$LOGFILE" "$EARLY_LOG") 2>&1

log "persistent log: ${LOGFILE#"$TREE/"}"

for tool in adb find sha256sum stat mktemp awk sed grep install sort tr wc date timeout tee od readlink; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required"
done

ADB=(adb)

select_device() {
    local states

    log "phase 1/7: checking adb server"
    timeout "$ADB_TIMEOUT" adb start-server >/dev/null ||
        fail "adb server did not start within ${ADB_TIMEOUT}s"

    log "adb devices:"
    adb devices -l

    if [ -n "$SERIAL" ]; then
        ADB=(adb -s "$SERIAL")
        log "waiting for requested device $SERIAL"
        timeout "$ADB_TIMEOUT" "${ADB[@]}" wait-for-device >/dev/null ||
            fail "device $SERIAL did not become available within ${ADB_TIMEOUT}s"
        return
    fi

    mapfile -t devices < <(adb devices | awk 'NR > 1 && $2 == "device" {print $1}')

    [ "${#devices[@]}" -eq 1 ] ||
        fail "connect exactly one authorized adb device or use --serial SERIAL"

    SERIAL="${devices[0]}"
    ADB=(adb -s "$SERIAL")
    log "selected device: $SERIAL"
}

select_device

shell_quote() {
    local value="$1"
    printf "'%s'" "${value//\'/\'\\\'\'}"
}

log "phase 2/7: checking shell access"
log "checking adb shell identity"
set +e
shell_uid_output="$(timeout "$REMOTE_TIMEOUT" "${ADB[@]}" shell id -u 2>&1)"
shell_uid_rc=$?
set -e

if [ "$DEBUG" -eq 1 ] || [ "$shell_uid_rc" -ne 0 ]; then
    printf '%s\n' "$shell_uid_output"
fi

if [ "$shell_uid_rc" -eq 124 ]; then
    fail "adb shell identity check timed out after ${REMOTE_TIMEOUT}s"
fi
[ "$shell_uid_rc" -eq 0 ] ||
    fail "adb shell identity check failed with exit code $shell_uid_rc"

shell_uid="$(printf '%s' "$shell_uid_output" | tr -d '\r\n')"

ROOT_MODE=""
if [ "$shell_uid" = "0" ]; then
    ROOT_MODE="adbd"
    log "root mode: adbd is already root"
else
    log "adb shell uid=$shell_uid"
    log "requesting root through su"
    log "unlock the phone and approve the Shell/root prompt now"

    set +e
    su_probe_output="$(
        timeout "$ROOT_TIMEOUT" \
            "${ADB[@]}" shell "su -c 'id -u; id; echo ROOT_PROBE_COMPLETE'" \
            2>&1
    )"
    su_probe_rc=$?
    set -e

    printf '%s\n' "$su_probe_output"

    if [ "$su_probe_rc" -eq 124 ]; then
        fail "root request timed out after ${ROOT_TIMEOUT}s; check the phone's root-manager prompt"
    fi
    [ "$su_probe_rc" -eq 0 ] ||
        fail "su root probe failed with exit code $su_probe_rc"

    printf '%s\n' "$su_probe_output" | tr -d '\r' | grep -qx '0' ||
        fail "su command did not report uid 0"

    printf '%s\n' "$su_probe_output" | grep -q 'ROOT_PROBE_COMPLETE' ||
        fail "su command did not exit cleanly"

    ROOT_MODE="su"
    log "root mode: su"
fi

root_shell() {
    local seconds="$1"
    local command="$2"
    local quoted

    debug "remote command (${seconds}s): $command"

    if [ "$ROOT_MODE" = "adbd" ]; then
        timeout "$seconds" "${ADB[@]}" shell "$command"
    else
        quoted="$(shell_quote "$command")"
        timeout "$seconds" "${ADB[@]}" shell "su -c $quoted"
    fi
}

root_exec_out() {
    local seconds="$1"
    local command="$2"
    local quoted

    debug "remote binary command (${seconds}s): $command"

    if [ "$ROOT_MODE" = "adbd" ]; then
        timeout "$seconds" "${ADB[@]}" exec-out "$command"
    else
        quoted="$(shell_quote "$command")"
        timeout "$seconds" "${ADB[@]}" exec-out "su -c $quoted"
    fi
}

log "phase 3/7: testing non-interactive root commands"
root_test="$(
    root_shell "$REMOTE_TIMEOUT" \
        "printf 'REMOTE_ROOT_OK uid='; id -u; printf ' shell='; basename \"\$0\""
)"
printf '%s\n' "$root_test"
printf '%s\n' "$root_test" | grep -q 'REMOTE_ROOT_OK uid=0' ||
    fail "non-interactive root command did not return uid 0"

log "phase 4/7: reading device properties in one adb call"
set +e
ALL_PROPS="$(timeout "$REMOTE_TIMEOUT" "${ADB[@]}" shell getprop 2>&1)"
props_rc=$?
set -e

if [ "$props_rc" -eq 124 ]; then
    fail "getprop timed out after ${REMOTE_TIMEOUT}s"
fi
[ "$props_rc" -eq 0 ] || fail "getprop failed with exit code $props_rc"

ALL_PROPS="$(printf '%s\n' "$ALL_PROPS" | tr -d '\r')"

prop_value() {
    local name="$1"
    printf '%s\n' "$ALL_PROPS" |
        sed -n "s/^\[$(printf '%s' "$name" | sed 's/[][\/.^$*+?(){}|]/\\&/g')\]: \[\(.*\)\]$/\1/p" |
        head -n 1
}

device_values="$(
    printf '%s\n' \
        "$(prop_value ro.product.device)" \
        "$(prop_value ro.product.vendor.device)" \
        "$(prop_value ro.product.odm.device)" \
        "$(prop_value ro.product.system.device)" \
        "$(prop_value ro.product.product.device)" \
        "$(prop_value ro.build.product)" |
        sed '/^$/d' |
        sort -u
)"

model_values="$(
    printf '%s\n' \
        "$(prop_value ro.product.model)" \
        "$(prop_value ro.product.vendor.model)" \
        "$(prop_value ro.product.odm.model)" \
        "$(prop_value ro.product.system.model)" \
        "$(prop_value ro.product.product.model)" \
        "$(prop_value ro.product.name)" \
        "$(prop_value ro.product.vendor.name)" \
        "$(prop_value ro.product.odm.name)" \
        "$(prop_value ro.boot.hardware.sku)" |
        sed '/^$/d' |
        sort -u
)"

slot_suffix="$(prop_value ro.boot.slot_suffix)"

log "device properties:"
printf '  %s\n' $device_values
log "model/SKU properties:"
printf '  %s\n' $model_values
log "slot suffix: ${slot_suffix:-unknown}"

device_is_supported=0
if printf '%s\n' "$device_values" | grep -Fxiq "$EXPECTED_DEVICE"; then
    device_is_supported=1
fi

detected_model="unknown"
for supported in "${SUPPORTED_MODELS[@]}"; do
    if printf '%s\n' "$model_values" |
       tr '[:lower:]' '[:upper:]' |
       grep -Fq "$supported"; then
        detected_model="$supported"
        device_is_supported=1
        break
    fi
done

if [ "$FORCE_DEVICE" -ne 1 ] && [ "$device_is_supported" -ne 1 ]; then
    printf 'Supported models: %s\n' "${SUPPORTED_MODELS[*]}" >&2
    fail "connected phone is not identified as a supported OnePlus 15"
fi

log "accepted device: codename=${EXPECTED_DEVICE}, model=${detected_model}"

if [ "$DIAGNOSE_ONLY" -eq 1 ]; then
    log "diagnostic checks passed"
    log "no files were searched, pulled, or overwritten"
    exit 0
fi

module_roots=(
    /vendor_dlkm/lib/modules
    /odm_dlkm/lib/modules
    /vendor/lib/modules
    /odm/lib/modules
    /system_dlkm/lib/modules
    /system/lib/modules
    /lib/modules
)

library64_roots=(
    /vendor/lib64
    /odm/lib64
    /system/lib64
    /system_ext/lib64
    /product/lib64
    /my_product/lib64
    /my_company/lib64
    /vendor/odm/lib64
    /apex
)

library32_roots=(
    /vendor/lib
    /odm/lib
    /system/lib
    /system_ext/lib
    /product/lib
    /my_product/lib
    /my_company/lib
    /vendor/odm/lib
    /apex
)

firmware_roots=(
    /vendor/etc/wifi
    /odm/etc/wifi
    /vendor/odm/etc/wifi
    /vendor/rfs/msm/wpss/readonly/firmware/image
    /system/etc/wifi
    /my_product/etc/wifi
    /my_company/etc/wifi
    /vendor/firmware
    /odm/firmware
    /vendor/odm/firmware
    /system/etc/firmware
    /my_product/firmware
    /my_company/firmware
    /lib/firmware
)

# Repository-wide .bin files may live outside the standard Wi-Fi/firmware
# directories. Exact partition-relative paths are always tried first. These
# roots are used only for a bounded basename fallback when no exact path exists.
binary_roots=(
    /vendor/rfs/msm/wpss/readonly/firmware/image
    /vendor/etc/wifi
    /odm/etc/wifi
    /vendor/odm/etc/wifi
    /vendor/firmware
    /odm/firmware
    /vendor/odm/firmware
    /system/etc/firmware
    /system_ext/etc/firmware
    /product/etc/firmware
    /my_product/firmware
    /my_company/firmware
    /lib/firmware
    /vendor/etc
    /odm/etc
    /system/etc
    /system_ext/etc
    /product/etc
    /my_product/etc
    /my_company/etc
    /vendor
    /odm
    /system
    /system_ext
    /product
    /my_product
    /my_company
)

stamp="$STARTED_AT"
work="$(mktemp -d "${TMPDIR:-/tmp}/infiniti-proprietary.XXXXXX")"
stage="$work/stage"
plan="$work/plan.tsv"
missing="$work/missing.tsv"

mkdir -p "$stage"
: > "$plan"
: > "$missing"
trap 'rm -rf "$work"' EXIT HUP INT TERM

log "phase 5/7: enumerating existing repository blobs"

local_files=()
declare -A seen_local_files=()

register_local_file() {
    local file="$1"
    local canonical

    [ -e "$file" ] || return 0

    if [ -L "$file" ]; then
        canonical="$(readlink -f "$file" 2>/dev/null || true)"
        case "$canonical" in
            "$TREE"/*)
                [ -f "$canonical" ] || return 0
                debug "repository symlink ${file#"$TREE/"} -> ${canonical#"$TREE/"}; refreshing target"
                file="$canonical"
                ;;
            *)
                warn "skipping external repository symlink: ${file#"$TREE/"}"
                return 0
                ;;
        esac
    fi

    [ -f "$file" ] || return 0
    [ -z "${seen_local_files[$file]+x}" ] || return 0
    seen_local_files[$file]=1
    local_files+=("$file")
}

# Every existing shared library, kernel module, and binary firmware image
# anywhere in the source tree. Generated output and VCS metadata are excluded.
while IFS= read -r -d '' file; do
    register_local_file "$file"
done < <(
    find "$TREE" \
        \( -path "$TREE/.git" -o -path "$TREE/out" \) -prune -o \
        \( -type f -o -type l \) \
        \( -name '*.ko' -o -name '*.so' -o -name '*.bin' \) \
        -print0 |
        sort -z
)

# Continue refreshing non-ELF Wi-Fi configuration and firmware payloads already
# packaged in the recovery ramdisk.
while IFS= read -r -d '' file; do
    register_local_file "$file"
done < <(
    find "$TREE/recovery/root" \
        \( -type f -o -type l \) \
        \( -path '*/etc/wifi/*' -o -path '*/firmware/*' \) \
        -print0 |
        sort -z
)

[ "${#local_files[@]}" -gt 0 ] ||
    fail "no existing .ko, .so, .bin, Wi-Fi, or firmware files were found in the repository"

# Sort the deduplicated list after resolving any in-tree symlinks.
mapfile -d '' -t local_files < <(printf '%s\0' "${local_files[@]}" | sort -zu)

module_count=0
library_count=0
binary_count=0
firmware_count=0
for file in "${local_files[@]}"; do
    case "$file" in
        *.ko) module_count=$((module_count + 1)) ;;
        *.so) library_count=$((library_count + 1)) ;;
        *.bin) binary_count=$((binary_count + 1)) ;;
        *) firmware_count=$((firmware_count + 1)) ;;
    esac
done

log "selected ${#local_files[@]} files: $module_count modules, $library_count shared libraries, $binary_count .bin files, $firmware_count other Wi-Fi/firmware files"

if [ "$LIST_LOCAL" -eq 1 ]; then
    for file in "${local_files[@]}"; do
        printf '%s\n' "${file#"$TREE/"}"
    done
    exit 0
fi

exact_candidates() {
    local kind="$1"
    local mapping_path="$2"
    local suffix
    local marker

    case "$kind" in
        module)
            if [[ "$mapping_path" == *lib/modules/* ]]; then
                suffix="${mapping_path#*lib/modules/}"
            else
                suffix="${mapping_path##*/}"
            fi
            printf '%s\n' \
                "/vendor_dlkm/lib/modules/$suffix" \
                "/odm_dlkm/lib/modules/$suffix" \
                "/vendor/lib/modules/$suffix" \
                "/odm/lib/modules/$suffix" \
                "/system_dlkm/lib/modules/$suffix" \
                "/system/lib/modules/$suffix" \
                "/lib/modules/$suffix"
            ;;
        library64|library32|library)
            # First preserve an existing partition-relative path. This handles
            # recovery/root/vendor/lib64/hw/foo.so and similar layouts.
            case "$mapping_path" in
                vendor/odm/*)
                    printf '%s\n' "/odm/${mapping_path#vendor/odm/}" "/$mapping_path"
                    ;;
                system/vendor/*)
                    printf '%s\n' "/vendor/${mapping_path#system/vendor/}" "/$mapping_path"
                    ;;
                vendor/*|odm/*|system/*|system_ext/*|product/*|my_product/*|my_company/*|apex/*)
                    printf '%s\n' "/$mapping_path"
                    ;;
            esac

            # Then preserve the suffix below a recognized library root even
            # when the source file lives below a repository prebuilt folder.
            for marker in \
                vendor/lib64 vendor/lib \
                odm/lib64 odm/lib \
                system/lib64 system/lib \
                system_ext/lib64 system_ext/lib \
                product/lib64 product/lib \
                my_product/lib64 my_product/lib \
                my_company/lib64 my_company/lib \
                vendor/odm/lib64 vendor/odm/lib; do
                case "$mapping_path" in
                    *"$marker"/*)
                        suffix="${mapping_path#*"$marker"/}"
                        printf '%s\n' "/$marker/$suffix"
                        case "$marker" in
                            vendor/odm/*) printf '%s\n' "/odm/${marker#vendor/odm/}/$suffix" ;;
                        esac
                        ;;
                esac
            done

            suffix="${mapping_path##*/}"
            case "$kind" in
                library64)
                    for marker in "${library64_roots[@]}"; do printf '%s\n' "$marker/$suffix"; done
                    ;;
                library32)
                    for marker in "${library32_roots[@]}"; do printf '%s\n' "$marker/$suffix"; done
                    ;;
                library)
                    for marker in "${library64_roots[@]}" "${library32_roots[@]}"; do printf '%s\n' "$marker/$suffix"; done
                    ;;
            esac
            ;;
        binary)
            # Preserve a direct partition-relative path first. This covers
            # recovery/root/vendor/..., vendor/..., odm/..., and similar trees.
            case "$mapping_path" in
                vendor/odm/*)
                    printf '%s\n' "/odm/${mapping_path#vendor/odm/}" "/$mapping_path"
                    ;;
                system/vendor/*)
                    printf '%s\n' "/vendor/${mapping_path#system/vendor/}" "/$mapping_path"
                    ;;
                vendor/*|odm/*|system/*|system_ext/*|product/*|my_product/*|my_company/*|apex/*)
                    printf '%s\n' "/$mapping_path"
                    ;;
            esac

            # Preserve the suffix below known firmware/config roots when the
            # repository stores the file under a prebuilt or copied subtree.
            for marker in \
                vendor/rfs/msm/wpss/readonly/firmware/image \
                vendor/etc/wifi odm/etc/wifi vendor/odm/etc/wifi \
                vendor/firmware odm/firmware vendor/odm/firmware \
                system/etc/firmware system_ext/etc/firmware \
                product/etc/firmware my_product/firmware my_company/firmware \
                lib/firmware; do
                case "$mapping_path" in
                    *"$marker"/*)
                        suffix="${mapping_path#*"$marker"/}"
                        printf '%s\n' "/$marker/$suffix"
                        case "$marker" in
                            vendor/odm/*)
                                printf '%s\n' "/odm/${marker#vendor/odm/}/$suffix"
                                ;;
                        esac
                        ;;
                esac
            done

            # Finally try a file directly below each known binary root before
            # falling back to a recursive basename search.
            suffix="${mapping_path##*/}"
            for marker in "${binary_roots[@]}"; do
                printf '%s\n' "$marker/$suffix"
            done
            ;;
        firmware)
            case "$mapping_path" in
                vendor/odm/etc/wifi/*)
                    suffix="${mapping_path#vendor/odm/etc/wifi/}"
                    printf '%s\n' \
                        "/vendor/rfs/msm/wpss/readonly/firmware/image/$suffix" \
                        "/odm/etc/wifi/$suffix" \
                        "/vendor/odm/etc/wifi/$suffix" \
                        "/vendor/etc/wifi/$suffix"
                    ;;
                */etc/wifi/*)
                    suffix="${mapping_path#*etc/wifi/}"
                    printf '%s\n' \
                        "/vendor/etc/wifi/$suffix" \
                        "/odm/etc/wifi/$suffix" \
                        "/vendor/odm/etc/wifi/$suffix" \
                        "/system/etc/wifi/$suffix" \
                        "/my_product/etc/wifi/$suffix" \
                        "/my_company/etc/wifi/$suffix" \
                        "/vendor/rfs/msm/wpss/readonly/firmware/image/$suffix"
                    ;;
                */firmware/*)
                    suffix="${mapping_path#*firmware/}"
                    printf '%s\n' \
                        "/vendor/firmware/$suffix" \
                        "/odm/firmware/$suffix" \
                        "/vendor/odm/firmware/$suffix" \
                        "/system/etc/firmware/$suffix" \
                        "/my_product/firmware/$suffix" \
                        "/my_company/firmware/$suffix" \
                        "/lib/firmware/$suffix"
                    ;;
            esac
            ;;
    esac
}

resolve_exact_source() {
    local kind="$1"
    local mapping_path="$2"
    local candidate
    local result
    local rc

    while IFS= read -r candidate; do
        [ -n "$candidate" ] || continue
        debug "checking exact path: $candidate"

        set +e
        result="$(
            root_shell "$REMOTE_TIMEOUT" \
                "if [ -r $(shell_quote "$candidate") ]; then printf '%s\\n' $(shell_quote "$candidate"); fi; exit 0"
        )"
        rc=$?
        set -e

        if [ "$rc" -eq 124 ]; then
            warn "exact-path check timed out: $candidate"
            continue
        fi
        [ "$rc" -eq 0 ] || continue

        result="$(printf '%s' "$result" | tr -d '\r')"
        if [ -n "$result" ]; then
            printf '%s\n' "$result"
            return 0
        fi
    done < <(exact_candidates "$kind" "$mapping_path")

    return 1
}

resolve_fallback_source() {
    local kind="$1"
    local relative_path="$2"
    local basename="${relative_path##*/}"
    local roots=()
    local root
    local output
    local rc
    local match
    local canonical
    local canonical_output
    local canonical_rc
    local matches=()
    declare -A seen_canonical=()

    case "$kind" in
        module) roots=("${module_roots[@]}") ;;
        library64) roots=("${library64_roots[@]}") ;;
        library32) roots=("${library32_roots[@]}") ;;
        library) roots=("${library64_roots[@]}" "${library32_roots[@]}") ;;
        binary) roots=("${binary_roots[@]}") ;;
        firmware) roots=("${firmware_roots[@]}") ;;
        *) fail "unknown blob kind: $kind" ;;
    esac

    log "fallback basename search: $basename"

    for root in "${roots[@]}"; do
        printf '[%s] [proprietary-files]   searching %s\n' "$(timestamp)" "$root" >&2

        set +e
        output="$(
            root_shell "$SEARCH_TIMEOUT" \
                "if [ -d $(shell_quote "$root") ]; then find $(shell_quote "$root") -name $(shell_quote "$basename") -print 2>/dev/null; fi; exit 0"
        )"
        rc=$?
        set -e

        if [ "$rc" -eq 124 ]; then
            warn "search timed out after ${SEARCH_TIMEOUT}s: $root"
            continue
        fi
        [ "$rc" -eq 0 ] || {
            warn "search returned rc=$rc for $root"
            continue
        }

        while IFS= read -r match; do
            match="${match//$'\r'/}"
            [ -n "$match" ] || continue
            case "$match" in
                /*) ;;
                *) warn "ignoring non-path search output: $match"; continue ;;
            esac

            set +e
            canonical_output="$(
                root_shell "$REMOTE_TIMEOUT" \
                    "readlink -f $(shell_quote "$match") 2>/dev/null || printf '%s\\n' $(shell_quote "$match")"
            )"
            canonical_rc=$?
            set -e

            if [ "$canonical_rc" -eq 124 ]; then
                canonical="$match"
            elif [ "$canonical_rc" -eq 0 ]; then
                canonical="$(printf '%s' "$canonical_output" | tr -d '\r\n')"
                [ -n "$canonical" ] || canonical="$match"
            else
                canonical="$match"
            fi

            if [ -z "${seen_canonical[$canonical]+x}" ]; then
                seen_canonical[$canonical]="$match"
                matches+=("$match")
            else
                debug "deduplicated alias $match -> $canonical"
            fi
        done <<< "$output"
    done

    if [ "${#matches[@]}" -eq 1 ]; then
        printf '%s\n' "${matches[0]}"
        return 0
    fi

    if [ "${#matches[@]}" -gt 1 ]; then
        warn "ambiguous source for $relative_path"
        printf '  %s\n' "${matches[@]}" >&2
    else
        warn "no source found for $relative_path"
    fi

    return 1
}

resolve_remote_source() {
    local kind="$1"
    local mapping_path="$2"
    local result

    if result="$(resolve_exact_source "$kind" "$mapping_path")"; then
        printf '%s\n' "$result"
        return 0
    fi

    resolve_fallback_source "$kind" "$mapping_path"
}

log "phase 6/7: resolving and staging blobs"

index=0
for destination in "${local_files[@]}"; do
    index=$((index + 1))
    repo_path="${destination#"$TREE/"}"
    mapping_path="$repo_path"
    case "$mapping_path" in
        recovery/root/*) mapping_path="${mapping_path#recovery/root/}" ;;
    esac

    case "$repo_path" in
        *.ko) kind="module" ;;
        *.so)
            case "/$mapping_path" in
                */lib64/*) kind="library64" ;;
                */lib/*) kind="library32" ;;
                *) kind="library" ;;
            esac
            ;;
        *.bin) kind="binary" ;;
        *) kind="firmware" ;;
    esac

    log "[$index/${#local_files[@]}] resolving $repo_path"

    if ! source_path="$(resolve_remote_source "$kind" "$mapping_path")"; then
        printf '%s\t%s\n' "$kind" "$repo_path" >> "$missing"
        continue
    fi

    source_path="$(printf '%s' "$source_path" | tr -d '\r')"
    case "$source_path" in
        /*) ;;
        *) fail "resolver returned an invalid source path for $repo_path: $source_path" ;;
    esac
    if [[ "$source_path" == *$'\n'* ]]; then
        fail "resolver returned multiple lines for $repo_path"
    fi

    log "[$index/${#local_files[@]}] pulling $source_path"

    staged_file="$stage/$repo_path"
    mkdir -p "$(dirname "$staged_file")"

    set +e
    remote_size="$(
        root_shell "$REMOTE_TIMEOUT" \
            "stat -c '%s' $(shell_quote "$source_path") 2>/dev/null"
    )"
    size_rc=$?
    set -e

    if [ "$size_rc" -eq 124 ]; then
        fail "remote size check timed out: $source_path"
    fi
    [ "$size_rc" -eq 0 ] || fail "could not read remote size: $source_path"
    remote_size="$(printf '%s' "$remote_size" | tr -d '\r\n ')"
    case "$remote_size" in
        ''|*[!0-9]*) fail "invalid remote size for $source_path: $remote_size" ;;
        0) fail "remote source is empty: $source_path" ;;
    esac

    set +e
    root_exec_out "$PULL_TIMEOUT" \
        "cat $(shell_quote "$source_path")" > "$staged_file"
    pull_rc=$?
    set -e

    if [ "$pull_rc" -eq 124 ]; then
        fail "pull timed out after ${PULL_TIMEOUT}s: $source_path"
    fi
    [ "$pull_rc" -eq 0 ] ||
        fail "pull failed with exit code $pull_rc: $source_path"

    [ -s "$staged_file" ] ||
        fail "extraction produced an empty file: $source_path"

    size="$(stat -c '%s' "$staged_file")"
    [ "$size" = "$remote_size" ] ||
        fail "size mismatch for $source_path: remote=$remote_size local=$size"

    case "$repo_path" in
        *.ko|*.so|*.elf)
            magic="$(od -An -tx1 -N4 "$staged_file" | tr -d ' \n')"
            [ "$magic" = "7f454c46" ] ||
                fail "invalid ELF magic for $repo_path: $magic"
            ;;
    esac

    old_sha="$(sha256sum "$destination" | awk '{print $1}')"
    new_sha="$(sha256sum "$staged_file" | awk '{print $1}')"

    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$kind" "$repo_path" "$source_path" \
        "$old_sha" "$new_sha" "$size" >> "$plan"

    log "[$index/${#local_files[@]}] staged ${size} bytes"
done

missing_count="$(wc -l < "$missing" | tr -d ' ')"

if [ "$missing_count" -gt 0 ]; then
    echo "Unresolved files:"
    while IFS=$'\t' read -r kind relative_path; do
        printf '  [%s] %s\n' "$kind" "$relative_path"
    done < "$missing"

    [ "$ALLOW_MISSING" -eq 1 ] ||
        fail "$missing_count files were unresolved; no device-tree files were overwritten"
fi

[ -s "$plan" ] || fail "no repository blobs could be extracted"

changed=0
unchanged=0

log "comparing staged files with the device tree"

while IFS=$'\t' read -r kind relative_path source_path old_sha new_sha size; do
    if [ "$old_sha" = "$new_sha" ]; then
        unchanged=$((unchanged + 1))
        printf '  unchanged %-8s %s\n' "$kind" "$relative_path"
    else
        changed=$((changed + 1))
        printf '  update    %-8s %s <- %s (%s bytes)\n' \
            "$kind" "$relative_path" "$source_path" "$size"
    fi
done < "$plan"

if [ "$DRY_RUN" -eq 1 ]; then
    log "dry run complete: $changed updates, $unchanged unchanged, $missing_count unresolved"
    exit 0
fi

log "phase 7/7: installing verified updates"

backup_dir="$TREE/out/proprietary-backup-$stamp"
manifest_dir="$TREE/out/proprietary-manifests"
manifest="$manifest_dir/proprietary-$stamp.tsv"

mkdir -p "$manifest_dir"

if [ "$BACKUP" -eq 1 ] && [ "$changed" -gt 0 ]; then
    mkdir -p "$backup_dir"
fi

{
    printf '# extracted_at\t%s\n' "$(date --iso-8601=seconds)"
    printf '# adb_serial\t%s\n' "$SERIAL"
    printf '# root_mode\t%s\n' "$ROOT_MODE"
    printf '# device_values\t%s\n' "$(printf '%s' "$device_values" | tr '\n' ',')"
    printf '# model_values\t%s\n' "$(printf '%s' "$model_values" | tr '\n' ',')"
    printf '# detected_model\t%s\n' "$detected_model"
    printf '# slot_suffix\t%s\n' "$slot_suffix"
    printf 'type\trepository_path\tphone_source\told_sha256\tnew_sha256\tsize_bytes\tstatus\n'
} > "$manifest"

install_index=0

while IFS=$'\t' read -r kind relative_path source_path old_sha new_sha size; do
    install_index=$((install_index + 1))
    destination="$TREE/$relative_path"
    staged_file="$stage/$relative_path"
    status="unchanged"

    if [ "$old_sha" != "$new_sha" ]; then
        status="updated"
        log "installing [$install_index] $relative_path"

        if [ "$BACKUP" -eq 1 ]; then
            previous="$backup_dir/$relative_path"
            mkdir -p "$(dirname "$previous")"
            cp -a "$destination" "$previous"
        fi

        mode="$(stat -c '%a' "$destination")"
        temporary="${destination}.new.$$"

        install -m "$mode" "$staged_file" "$temporary"
        mv -f "$temporary" "$destination"

        installed_sha="$(sha256sum "$destination" | awk '{print $1}')"
        [ "$installed_sha" = "$new_sha" ] ||
            fail "post-install hash verification failed: $relative_path"
    fi

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$kind" "$relative_path" "$source_path" \
        "$old_sha" "$new_sha" "$size" "$status" >> "$manifest"
done < "$plan"

while IFS=$'\t' read -r kind relative_path; do
    printf '%s\t%s\t\t\t\t\tmissing\n' \
        "$kind" "$relative_path" >> "$manifest"
done < "$missing"

log "complete: $changed updated, $unchanged unchanged, $missing_count unresolved"
log "manifest: ${manifest#"$TREE/"}"

if [ "$BACKUP" -eq 1 ] && [ "$changed" -gt 0 ]; then
    log "previous files: ${backup_dir#"$TREE/"}"
fi

log "review with: git status --short && git diff --stat"
log "debug log: ${LOGFILE#"$TREE/"}"
