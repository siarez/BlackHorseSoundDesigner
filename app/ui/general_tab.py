from __future__ import annotations
from PySide6 import QtWidgets, QtCore

from ..device_interface.cdc_link import CdcLink, auto_detect_port


class GeneralTab(QtWidgets.QWidget):
    """General device utilities.

    Provides a dangerous-but-useful action to erase the entire EEPROM journal
    on the MCU by issuing the firmware console command:
        !fill 0 32768 255
    which fills the 32 KiB 24C256 with 0xFF.
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        info = QtWidgets.QLabel(
            "Utilities for device bring-up and recovery.\n"
            "Erase EEPROM clears the entire on-board journal (all records)."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self.btn_erase = QtWidgets.QPushButton("Erase EEPROM (Journal)")
        self.btn_erase.setToolTip("Fills the whole 24C256 with 0xFF via firmware !fill command")
        self.btn_erase.clicked.connect(self._on_erase)
        root.addWidget(self.btn_erase)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: palette(mid)")
        root.addWidget(self.lbl_status)

        root.addStretch(1)

    def _on_erase(self):
        if not self._confirm():
            return
        self.btn_erase.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText("Erasing EEPROM… this can take a few seconds…")
        QtWidgets.QApplication.processEvents()

        port = auto_detect_port()
        if not port:
            QtWidgets.QMessageBox.warning(self, 'Erase EEPROM', 'No device found (auto-detect failed)')
            self._restore_after(old_cursor)
            return
        try:
            link = CdcLink(port)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Erase EEPROM', f'Failed to open {port}: {e}')
            self._restore_after(old_cursor)
            return

        try:
            # Ensure EEPROM driver is initialized on device
            try:
                link._write_line("!ei")
            except Exception:
                pass
            # Issue fill for full 32 KiB at value 0xFF
            link._write_line("!fill 0 32768 255")
            # Wait for OK/ERR response; allow generous timeout
            ok = self._wait_for_fill_result(link, timeout_s=30.0)
            if ok:
                self.lbl_status.setText("EEPROM erase completed (OK FILL).")
                QtWidgets.QMessageBox.information(self, 'Erase EEPROM', 'Completed: EEPROM erased')
            else:
                self.lbl_status.setText("EEPROM erase failed or timed out.")
                QtWidgets.QMessageBox.warning(self, 'Erase EEPROM', 'Failed: no OK FILL received')
        finally:
            try:
                link.close()
            except Exception:
                pass
            self._restore_after(old_cursor)

    def _confirm(self) -> bool:
        m = QtWidgets.QMessageBox(self)
        m.setIcon(QtWidgets.QMessageBox.Warning)
        m.setWindowTitle('Erase EEPROM')
        m.setText('Erase the entire EEPROM journal?')
        m.setInformativeText('This removes all saved records (EQ, config, etc.).\nUse only for recovery.')
        m.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        m.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        return m.exec() == QtWidgets.QMessageBox.Ok

    def _wait_for_fill_result(self, link: CdcLink, timeout_s: float = 30.0) -> bool:
        """Poll lines until OK/ERR FILL appears or timeout."""
        import time
        dl = 0.2
        t0 = time.time()
        while (time.time() - t0) < timeout_s:
            lines = link.read_lines(dl)
            for ln in lines:
                s = (ln or '').strip().upper()
                if s.startswith('OK FILL'):
                    return True
                if s.startswith('ERR FILL'):
                    return False
            QtWidgets.QApplication.processEvents()
        return False

    def _restore_after(self, old_cursor):
        try:
            self.setCursor(old_cursor)
        except Exception:
            pass
        self.btn_erase.setEnabled(True)

