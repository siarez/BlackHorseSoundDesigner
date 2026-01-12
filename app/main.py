import os
import sys
import argparse
from PySide6.QtWidgets import QApplication, QStyleFactory
from app.ui.main_window import MainWindow
from app.ui.palette import apply_palette, Theme

def main():
    # Parse our CLI first, leave remaining args for Qt
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--dev', action='store_true', help='Show developer tabs and Export action')
    # Keep unknown args for Qt
    args, qt_argv = ap.parse_known_args(sys.argv)

    app = QApplication(qt_argv)
    # Use a uniform, cross‑platform style across OSes
    app.setStyle(QStyleFactory.create("Fusion"))
    # Apply theme (default light). Allow override via env QT_THEME=dark|light
    theme_env = os.environ.get('QT_THEME', '').strip().lower()
    theme = Theme.DARK if theme_env == 'dark' else Theme.LIGHT
    apply_palette(app, theme)
    w = MainWindow(dev_mode=bool(args.dev))
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
