#!/usr/bin/env bash
# Sync generated/lvgl_python.c, lv_conf.h, python/display_driver.py, python/fs_driver.py, and the lvgl submodule pin
# from PyDevices/lvgl-bindings
# on GitHub (not the local workspace).
#
# Usage:
#   ./scripts/sync_from_lvgl_bindings.sh --ref <40-character commit SHA>
#   ./scripts/sync_from_lvgl_bindings.sh --ref v9.5.N
#
# After syncing, commit the updated files and lvgl submodule SHA in this repo.

set -euo pipefail

LV_BINDINGS_REPO="${LV_BINDINGS_REPO:-https://github.com/PyDevices/lvgl-bindings.git}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_REPO="$(cd "$SCRIPT_DIR/.." && pwd)"

REF="${LV_BINDINGS_REF:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ref)
            REF=$2
            shift 2
            ;;
        --help | -h)
            sed -n '2,12p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$REF" ]]; then
    REF=$(tr -d '[:space:]' < "$SOURCE_REPO/LVGL_BINDINGS_COMMIT")
fi
if [[ ! "$REF" =~ ^[0-9a-fA-F]{40}$ && ! "$REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: --ref must be an exact 40-character commit SHA or vX.Y.Z tag, got: $REF" >&2
    exit 1
fi

# Short-lived clone under /tmp so we never read the local sibling lvgl-bindings tree.
TMP=$(mktemp -d)
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "Fetching ${LV_BINDINGS_REPO} @ ${REF}..."
echo "(using temp clone ${TMP}/lvgl-bindings — removed on exit)"
git clone --filter=blob:none --no-checkout "${LV_BINDINGS_REPO}" "${TMP}/lvgl-bindings"
git -C "${TMP}/lvgl-bindings" fetch origin "$REF"
RESOLVED_REF=$(git -C "${TMP}/lvgl-bindings" rev-parse 'FETCH_HEAD^{commit}')

echo "Checking out generated/lvgl_python.c, generated/lvgl.pyi, lv_conf.h, python/display_driver.py, and python/fs_driver.py..."
git -C "${TMP}/lvgl-bindings" checkout "$RESOLVED_REF" -- generated/lvgl_python.c generated/lvgl.pyi lv_conf.h python/display_driver.py python/fs_driver.py

LVPY_SRC="${TMP}/lvgl-bindings/generated/lvgl_python.c"
LVPYI_SRC="${TMP}/lvgl-bindings/generated/lvgl.pyi"
LV_CONF_SRC="${TMP}/lvgl-bindings/lv_conf.h"
if [[ ! -f "$LVPY_SRC" ]]; then
    echo "Error: generated/lvgl_python.c not found on ${REF}." >&2
    echo "Regenerate and commit generated/lvgl_python.c in lvgl-bindings first." >&2
    exit 1
fi
if [[ ! -f "$LVPYI_SRC" ]]; then
    echo "Error: generated/lvgl.pyi not found on ${REF}." >&2
    echo "Regenerate and commit generated/lvgl.pyi in lvgl-bindings first." >&2
    exit 1
fi
if [[ ! -f "$LV_CONF_SRC" ]]; then
    echo "Error: lv_conf.h not found on ${REF}." >&2
    exit 1
fi

# Read the pinned lvgl commit from git metadata — no submodule clone (avoids SSH URLs).
echo "Reading lvgl submodule pin from lvgl-bindings..."
LVGL_SHA=$(git -C "${TMP}/lvgl-bindings" ls-tree "$RESOLVED_REF" lvgl | awk '{print $3}')
if [[ -z "$LVGL_SHA" || "$LVGL_SHA" == "lvgl" ]]; then
    echo "Error: could not read lvgl submodule commit from lvgl-bindings ${REF}." >&2
    exit 1
fi

mkdir -p "${SOURCE_REPO}/generated"
cp "$LVPY_SRC" "${SOURCE_REPO}/generated/lvgl_python.c"
cp "$LVPYI_SRC" "${SOURCE_REPO}/generated/lvgl.pyi"
cp "$LV_CONF_SRC" "${SOURCE_REPO}/lv_conf.h"
printf '%s\n' "$RESOLVED_REF" > "${SOURCE_REPO}/LVGL_BINDINGS_COMMIT"

for helper in display_driver.py fs_driver.py; do
    HELPER_SRC="${TMP}/lvgl-bindings/python/${helper}"
    if [[ ! -f "$HELPER_SRC" ]]; then
        echo "Error: python/${helper} not found on ${REF}." >&2
        exit 1
    fi
    cp "$HELPER_SRC" "${SOURCE_REPO}/${helper}"
done

cd "${SOURCE_REPO}"
if [[ ! -f .gitmodules ]]; then
    echo "Error: lvgl submodule not configured in this repo." >&2
    exit 1
fi

echo "Updating local lvgl submodule to ${LVGL_SHA}..."
git submodule update --init lvgl
git -C lvgl fetch origin "${LVGL_SHA}" 2>/dev/null || git -C lvgl fetch origin
git -C lvgl checkout "${LVGL_SHA}"

echo
echo "Synced from lvgl-bindings ${RESOLVED_REF}:"
echo "  LVGL_BINDINGS_COMMIT"
echo "  generated/lvgl_python.c"
echo "  generated/lvgl.pyi"
echo "  lv_conf.h"
echo "  display_driver.py"
echo "  fs_driver.py"
echo "  lvgl @ ${LVGL_SHA}"
echo
echo "Commit when ready:"
echo "  git add LVGL_BINDINGS_COMMIT generated/lvgl_python.c generated/lvgl.pyi lv_conf.h display_driver.py fs_driver.py lvgl"
echo "  git commit -m \"Sync bindings and LVGL from lvgl-bindings ${RESOLVED_REF}.\""
