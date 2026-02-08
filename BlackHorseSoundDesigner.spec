# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(globals().get("SPECPATH", os.getcwd())).resolve()
APP_NAME = "BlackHorseSoundDesigner"
APP_DISPLAY_NAME = "Black Horse Sound Designer"
APP_BUNDLE_ID = "com.blackhorseaudio.sounddesigner"
ICON_FILE = ROOT / "app" / "assets" / "icons" / ("horse_logo.icns" if sys.platform == "darwin" else "horse_logo.ico")
ICON_PATH = str(ICON_FILE) if ICON_FILE.exists() else None

datas = [
    (str(ROOT / "app" / "eqcore" / "maps"), "app/eqcore/maps"),
    (str(ROOT / "app" / "assets"), "app/assets"),
    (str(ROOT / "example_configs"), "example_configs"),
    (str(ROOT / "docs"), "docs"),
]

hiddenimports = collect_submodules("pyqtgraph")


a = Analysis(
    ["app/main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=ICON_PATH,
        bundle_identifier=APP_BUNDLE_ID,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_DISPLAY_NAME,
            "NSHighResolutionCapable": True,
        },
    )
