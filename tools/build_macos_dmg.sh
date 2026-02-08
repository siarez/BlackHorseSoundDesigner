#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only runs on macOS." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_SCRIPT="${REPO_ROOT}/tools/build_pyinstaller.sh"
APP_PATH="${REPO_ROOT}/dist/BlackHorseSoundDesigner.app"
STAGE_DIR="${REPO_ROOT}/dist/.dmg-staging"
DMG_PATH="${REPO_ROOT}/dist/BlackHorseSoundDesigner.dmg"

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "hdiutil not found; required on macOS to create DMG." >&2
  exit 1
fi

echo "[1/4] Building app bundle..."
"${BUILD_SCRIPT}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "App bundle not found at: ${APP_PATH}" >&2
  echo "Check PyInstaller build output and spec." >&2
  exit 1
fi

echo "[2/4] Preparing DMG staging..."
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"
cp -R "${APP_PATH}" "${STAGE_DIR}/"
ln -s /Applications "${STAGE_DIR}/Applications"

echo "[3/4] Creating DMG..."
rm -f "${DMG_PATH}"
hdiutil create \
  -volname "BlackHorseSoundDesigner" \
  -srcfolder "${STAGE_DIR}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

echo "[4/4] Done."
echo "DMG:"
echo "  ${DMG_PATH}"
