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
