#!/usr/bin/env bash
set -euo pipefail
device="$(cd "$(dirname "$0")/.." && pwd)"
root="$(cd "$device/../../.." && pwd)"
revision=c7996bb97601a7f04d3e5c371317425da9b82ba4
dst="$device/smb/upstream"
if [ ! -d "$dst/.git" ]; then
    mkdir -p "$dst"
    git -C "$dst" init -q
    git -C "$dst" remote add origin https://github.com/sahlberg/libsmb2.git
fi
if ! git -C "$dst" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$dst" fetch --depth=1 origin "$revision"
fi
test -z "$(git -C "$dst" status --porcelain)"
git -C "$dst" switch --detach "$revision"
for project in external/libfuse system/sepolicy; do
    patch="$device/patches/smb/${project//\//-}.patch"
    if ! git -C "$root/$project" apply --reverse --check "$patch" 2>/dev/null; then
        git -C "$root/$project" apply --check "$patch"
        git -C "$root/$project" apply "$patch"
    fi
done
