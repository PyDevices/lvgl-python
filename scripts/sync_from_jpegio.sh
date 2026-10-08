#!/usr/bin/env bash
# Sync jpegio's LVGL JPEG decoder (lvgl_decoder.c/.h and its TJpgDec) from
# PyDevices/micropython-pydevices on GitHub (not the local workspace) into
# src/jpegio/, and record the commit in JPEGIO_COMMIT.
#
# The same decoder serves LVGL on MicroPython and CircuitPython, so a JPEG
# draws the same way on every interpreter, scaled and transformed included.
#
# Usage:
#   ./scripts/sync_from_jpegio.sh --ref <40-character commit SHA>
#
# After syncing, commit JPEGIO_COMMIT and src/jpegio/.

set -euo pipefail

JPEGIO_REPO="${JPEGIO_REPO:-https://github.com/PyDevices/micropython-pydevices.git}"
JPEGIO_PATH="modules/jpegio/src"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"

REF="${JPEGIO_REF:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref)
            REF=$2
            shift 2
            ;;
        --help | -h)
            sed -n '2,13p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$REF" ]]; then
    REF=$(tr -d '[:space:]' < "$SOURCE_REPO/JPEGIO_COMMIT")
fi
if [[ ! "$REF" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "Error: --ref must be an exact 40-character commit SHA, got: $REF" >&2
    exit 1
fi

TMP=$(mktemp -d)
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "Fetching ${JPEGIO_REPO} @ ${REF}..."
git clone --filter=blob:none --no-checkout "${JPEGIO_REPO}" "${TMP}/src"
git -C "${TMP}/src" fetch origin "$REF"
RESOLVED_REF=$(git -C "${TMP}/src" rev-parse 'FETCH_HEAD^{commit}')
git -C "${TMP}/src" checkout "$RESOLVED_REF" -- \
    "${JPEGIO_PATH}/lvgl_decoder.c" "${JPEGIO_PATH}/lvgl_decoder.h" "${JPEGIO_PATH}/tjpgd"

DEST="${SOURCE_REPO}/src/jpegio"
rm -rf "$DEST"
mkdir -p "$DEST/tjpgd"
cp "${TMP}/src/${JPEGIO_PATH}/lvgl_decoder.c" "${TMP}/src/${JPEGIO_PATH}/lvgl_decoder.h" "$DEST/"
cp "${TMP}/src/${JPEGIO_PATH}/tjpgd/"* "$DEST/tjpgd/"
printf '%s\n' "$RESOLVED_REF" > "${SOURCE_REPO}/JPEGIO_COMMIT"

echo
echo "Synced jpegio's LVGL decoder from micropython-pydevices ${RESOLVED_REF}:"
echo "  JPEGIO_COMMIT"
echo "  src/jpegio/"
