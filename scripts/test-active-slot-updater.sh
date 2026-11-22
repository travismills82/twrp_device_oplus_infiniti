#!/usr/bin/env bash
set -euo pipefail

device="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
root="$(cd -- "${1:-"$device/../../.."}" && pwd)"
temp="$(mktemp -d)"
trap 'rm -f -- "$temp/bin" "$temp/payload" "$temp/recovery_a" "$temp/recovery_b"; rmdir "$temp"' EXIT
json="$root/external/jsoncpp"
"${CXX:-g++}" -std=c++17 -Wall -Wextra -Werror -I "$json/include" \
    "$device/scripts/test-active-slot-updater.cpp" "$json"/src/lib_json/json_{reader,value,writer}.cpp \
    -lcrypto -o "$temp/bin"
"$temp/bin" "$temp"
python3 -B "$device/scripts/test-active-slot-updater-ui.py" "$root"
