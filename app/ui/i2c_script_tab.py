from __future__ import annotations

from typing import List, Tuple
from PySide6 import QtWidgets

from ..device_interface.cdc_link import CdcLink, auto_detect_port


class I2cScriptTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._link: CdcLink | None = None

        self.port_combo = QtWidgets.QComboBox(self)
        self.auto_btn = QtWidgets.QPushButton("Auto-Detect", self)
        self.connect_btn = QtWidgets.QPushButton("Connect", self)
        self.run_btn = QtWidgets.QPushButton("Run Script", self)
        self.status_lbl = QtWidgets.QLabel("Disconnected", self)

        self.input = QtWidgets.QPlainTextEdit(self)
        self.input.setPlaceholderText("Paste I2C writes here, e.g.:\n\n// comment\nw 0x20 0x04 0x07\nw 0x20 0x02 0x00\n")
        self.input.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.output = QtWidgets.QPlainTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:"))
        top.addWidget(self.port_combo, 1)
        top.addWidget(self.auto_btn)
        top.addWidget(self.connect_btn)
        top.addWidget(self.run_btn)
        top.addWidget(self.status_lbl)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(QtWidgets.QLabel("I2C Write Script:"))
        root.addWidget(self.input, 1)
        root.addWidget(QtWidgets.QLabel("Log:"))
        root.addWidget(self.output, 1)

        self.auto_btn.clicked.connect(self._on_auto)
        self.connect_btn.clicked.connect(self._on_connect)
        self.run_btn.clicked.connect(self._on_run)

        self._populate_ports()

    def _populate_ports(self):
        self.port_combo.clear()
        dev = auto_detect_port()
        if dev:
            self.port_combo.addItem(dev, dev)
            self.port_combo.setCurrentIndex(0)

    def _ensure_link(self) -> bool:
        if self._link is not None:
            return True
        idx = self.port_combo.currentIndex()
        if idx < 0:
            QtWidgets.QMessageBox.warning(self, "I2C", "Select a serial port or use Auto-Detect.")
            return False
        dev = self.port_combo.itemData(idx) or self.port_combo.currentText()
        if not dev:
            QtWidgets.QMessageBox.warning(self, "I2C", "Serial port is empty.")
            return False
        try:
            self._link = CdcLink(dev)
            self.status_lbl.setText(f"Connected: {dev}")
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Connect", str(e))
            self._link = None
            return False

    def _on_auto(self):
        self._populate_ports()

    def _on_connect(self):
        if self._link is None:
            self._ensure_link()
            if self._link is not None:
                self.connect_btn.setText("Disconnect")
        else:
            try:
                self._link.close()
            except Exception:
                pass
            self._link = None
            self.connect_btn.setText("Connect")
            self.status_lbl.setText("Disconnected")

    def _parse_script(self, text: str) -> List[Tuple[int,int,int,int]]:
        out: List[Tuple[int,int,int,int]] = []
        for idx, raw in enumerate(text.splitlines(), start=1):
            line = raw.split('//', 1)[0].strip()
            if not line:
                continue
            toks = line.split()
            if toks[0].lower() == 'w' and len(toks) >= 4:
                try:
                    a = int(toks[1], 0); r = int(toks[2], 0); v = int(toks[3], 0)
                except Exception:
                    out.append((idx, -1, -1, -1)); continue
                out.append((idx, a, r, v))
            elif toks[0].lower() == 'r' and len(toks) >= 3:
                try:
                    a = int(toks[1], 0); r = int(toks[2], 0)
                except Exception:
                    out.append((idx, -1, -1, -1)); continue
                out.append((idx, a, r, -999))  # sentinel for read
            else:
                continue
        return out

    def _on_run(self):
        if not self._ensure_link():
            return
        cmds = self._parse_script(self.input.toPlainText())
        if not cmds:
            QtWidgets.QMessageBox.information(self, "I2C", "No commands to run.")
            return
        self.output.clear()
        ok_all = True
        for ln, a, r, v in cmds:
            # Accept sentinel v == -999 for reads
            if a < 0 or r < 0 or (v < 0 and v != -999):
                self.output.appendPlainText(f"Line {ln}: parse error")
                ok_all = False
                continue
            if v == -999:
                val = self._link.i2c_read(a, r)
                if val is None:
                    self.output.appendPlainText(f"Line {ln}: r {a:#x} {r:#x} -> ERR")
                    ok_all = False
                else:
                    self.output.appendPlainText(f"Line {ln}: r {a:#x} {r:#x} -> OK 0x{val:02X}")
            else:
                ok = self._link.i2c_write(a, r, v)
                self.output.appendPlainText(f"Line {ln}: w {a:#x} {r:#x} {v:#x} -> {'OK' if ok else 'ERR'}")
                if not ok:
                    ok_all = False
        self.output.appendPlainText("Done: all OK" if ok_all else "Done: with errors")
