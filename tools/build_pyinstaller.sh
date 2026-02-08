#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPEC_FILE="${REPO_ROOT}/BlackHorseSoundDesigner.spec"

if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "Spec file not found: ${SPEC_FILE}" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "${REPO_ROOT}"

echo "[1/3] Checking PyInstaller..."
"${PYTHON_BIN}" -c "import PyInstaller" >/dev/null 2>&1 || {
  echo "PyInstaller is not installed for ${PYTHON_BIN}." >&2
  echo "Install with: ${PYTHON_BIN} -m pip install pyinstaller" >&2
  exit 1
}

echo "[2/3] Building executable..."
"${PYTHON_BIN}" -m PyInstaller --noconfirm --clean "${SPEC_FILE}"

echo "[3/3] Done."
if [[ -d "${REPO_ROOT}/dist/BlackHorseSoundDesigner.app" ]]; then
  echo "Output app bundle:"
  echo "  ${REPO_ROOT}/dist/BlackHorseSoundDesigner.app"
  echo
  echo "Run on this machine:"
  echo "  open '${REPO_ROOT}/dist/BlackHorseSoundDesigner.app'"
else
  echo "Output directory:"
  echo "  ${REPO_ROOT}/dist/BlackHorseSoundDesigner"
  echo
  echo "Run on this machine:"
  echo "  ${REPO_ROOT}/dist/BlackHorseSoundDesigner/BlackHorseSoundDesigner"
fi
