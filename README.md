# Black Horse Sound Designer
This app is developed for configuring the Shabrang amplifier board and programming its DSP.
To run: `uv run -m app.main`

## Build Executable (PyInstaller)

1. Install build dependency:
   `python3 -m pip install pyinstaller`
2. Build:
   `./tools/build_pyinstaller.sh`
3. Run:
   `./dist/BlackHorseSoundDesigner/BlackHorseSoundDesigner`

Notes:
- Builds are OS-specific. Build on each target OS (macOS/Windows/Linux).
- The spec bundles `app/eqcore/maps`, `example_configs`, and `docs`.

## macOS App + DMG (Recommended Distribution)

Build a native `.app` bundle and a drag-and-drop `.dmg`:

1. Build app bundle:
   `./tools/build_pyinstaller.sh`
2. Build DMG:
   `./tools/build_macos_dmg.sh`

Output:
- App bundle: `dist/BlackHorseSoundDesigner.app`
- DMG installer: `dist/BlackHorseSoundDesigner.dmg`

End-user flow:
- Download DMG.
- Open DMG and drag `BlackHorseSoundDesigner.app` to `Applications`.
- Launch from `Applications`.

## Windows Installer (Recommended Distribution)

Build on a Windows machine.

Prerequisites:
- Python with project dependencies
- PyInstaller: `python -m pip install pyinstaller`
- Inno Setup (for `iscc` in PATH)

Build installer:
`powershell -ExecutionPolicy Bypass -File .\tools\build_windows_installer.ps1`

Output:
- Installer EXE in `dist\`
- Filename pattern: `BlackHorseSoundDesigner-Setup-<version>.exe`

End-user flow:
- Download installer EXE.
- Run installer.
- Launch from Start Menu (or desktop icon if selected during install).
