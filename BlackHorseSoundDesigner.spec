# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(globals().get("SPECPATH", os.getcwd())).resolve()

datas = [
    (str(ROOT / "app" / "eqcore" / "maps"), "app/eqcore/maps"),
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
    name="BlackHorseSoundDesigner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BlackHorseSoundDesigner",
)
