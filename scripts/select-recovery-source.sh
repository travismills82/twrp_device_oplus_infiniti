#!/usr/bin/env bash
# Select the device's supported XML GUI base without cleaning/resetting edits.
set -euo pipefail
DEVICE_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="${1:-$(CDPATH= cd -- "$DEVICE_DIR/../../.." && pwd)}"
RECOVERY="$SOURCE_ROOT/bootable/recovery"
EXPECTED="$(tr -d '\r\n' < "$DEVICE_DIR/config/recovery-source-revision.txt")"
[[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid recovery revision' >&2; exit 1; }
CURRENT="$(git -C "$RECOVERY" rev-parse HEAD)"
if [ "$CURRENT" = "$EXPECTED" ]; then
    echo "Supported recovery source already selected: $EXPECTED"
    exit 0
fi
if [ -n "$(git -C "$RECOVERY" status --porcelain)" ]; then
    echo 'Refusing to change a dirty recovery checkout. Preserve/reconcile edits first.' >&2
    exit 1
fi
if ! git -C "$RECOVERY" cat-file -e "$EXPECTED^{commit}" 2>/dev/null; then
    REMOTE="$(git -C "$RECOVERY" remote | head -n 1)"
    [ -n "$REMOTE" ] || { echo 'No recovery remote for the pinned commit' >&2; exit 1; }
    git -C "$RECOVERY" fetch --depth=1 "$REMOTE" "$EXPECTED"
fi
git -C "$RECOVERY" switch --detach "$EXPECTED"
echo "Selected XML GUI recovery source: $EXPECTED (previous HEAD: $CURRENT)"
