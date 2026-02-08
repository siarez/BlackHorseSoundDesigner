import os
import sys
import argparse
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyleFactory
from app.ui.main_window import MainWindow
from app.ui.palette import apply_palette, Theme

def _find_app_icon() -> Path | None:
    """Return path to app icon if present (source or PyInstaller bundle)."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.extend([
            base / "app/assets/icons/horse_logo.png",
            base / "app/assets/icons/horse_logo.icns",
            base / "app/assets/icons/horse_logo.ico",
            base / "assets/icons/horse_logo.png",
            base / "assets/icons/horse_logo.icns",
            base / "assets/icons/horse_logo.ico",
        ])
    root = Path(__file__).resolve().parents[1]
    candidates.extend([
        root / "app/assets/icons/horse_logo.png",
        root / "app/assets/icons/horse_logo.icns",
        root / "app/assets/icons/horse_logo.ico",
        root / "assets/icons/horse_logo.png",
        root / "assets/icons/horse_logo.icns",
        root / "assets/icons/horse_logo.ico",
    ])
    for p in candidates:
        if p.exists():
            return p
    return None

def main():
    # Parse our CLI first, leave remaining args for Qt
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--dev', action='store_true', help='Show developer tabs and Export action')
    ap.add_argument('--meter', action='store_true', help='Show right-side level meter panel (default: on)')
    ap.add_argument('--no-meter', action='store_true', help='Disable right-side level meter panel')
    # Keep unknown args for Qt
    args, qt_argv = ap.parse_known_args(sys.argv)

    app = QApplication(qt_argv)
    # Use a uniform, cross‑platform style across OSes
    app.setStyle(QStyleFactory.create("Fusion"))
    # Apply theme (default light). Allow override via env QT_THEME=dark|light
    theme_env = os.environ.get('QT_THEME', '').strip().lower()
    theme = Theme.DARK if theme_env == 'dark' else Theme.LIGHT
    apply_palette(app, theme)
    icon_path = _find_app_icon()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    # Meter panel defaults ON; --no-meter disables it. --meter kept for compatibility.
    show_meter = False if args.no_meter else True if not args.meter else True
    w = MainWindow(dev_mode=bool(args.dev), show_meter=show_meter)
    if icon_path is not None:
        w.setWindowIcon(QIcon(str(icon_path)))
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
