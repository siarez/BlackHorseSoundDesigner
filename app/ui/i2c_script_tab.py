from __future__ import annotations

from typing import List, Tuple
from PySide6 import QtWidgets

from ..device_interface.cdc_link import auto_detect_port, list_serial_ports
from ..device_interface.device_link_manager import get_device_link_manager


class I2cScriptTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_mgr = get_device_link_manager()
        self._connected_port: str = ""

        self.port_combo = QtWidgets.QComboBox(self)
        self.refresh_btn = QtWidgets.QPushButton("Refresh", self)
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
        top.addWidget(self.refresh_btn)
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

        self.refresh_btn.clicked.connect(self._on_refresh)
        self.auto_btn.clicked.connect(self._on_auto)
        self.connect_btn.clicked.connect(self._on_connect)
        self.run_btn.clicked.connect(self._on_run)

        self._populate_ports(auto_select=True)
        self._apply_connection_state(False)

    def _apply_connection_state(self, connected: bool, port: str = ""):
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.port_combo.setEnabled(not connected)
        self.refresh_btn.setEnabled(not connected)
        self.auto_btn.setEnabled(not connected)
        if connected:
            self.status_lbl.setText(f"Connected: {port}")
        else:
            self.status_lbl.setText("Disconnected")

    def _populate_ports(self, auto_select: bool = False):
        current = self.port_combo.itemData(self.port_combo.currentIndex()) if self.port_combo.currentIndex() >= 0 else ""
        sel_index = -1
        self.port_combo.clear()
        ports = list_serial_ports()
        for p in ports:
            label = f"{p.get('device','')} — {p.get('product','') or p.get('description','')} ({p.get('manufacturer','')})"
            self.port_combo.addItem(label, p.get('device', ''))
        if auto_select:
            dev = auto_detect_port()
            if dev:
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == dev:
                        sel_index = i
                        break
        elif current:
            for i in range(self.port_combo.count()):
                if self.port_combo.itemData(i) == current:
                    sel_index = i
                    break
        if sel_index >= 0:
            self.port_combo.setCurrentIndex(sel_index)
        elif self.port_combo.count() > 0:
            self.port_combo.setCurrentIndex(0)

    def _ensure_link(self) -> bool:
        if self._connected_port:
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
            self._connected_port = self._link_mgr.connect(port=dev, auto=False)
            self._apply_connection_state(True, self._connected_port)
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Connect", str(e))
            self._connected_port = ""
            self._apply_connection_state(False)
            return False

    def _on_refresh(self):
        self._populate_ports(auto_select=False)

    def _on_auto(self):
        self._populate_ports(auto_select=True)

    def _on_connect(self):
        if not self._connected_port:
            self._ensure_link()
        else:
            try:
                self._link_mgr.disconnect()
            except Exception:
                pass
            self._connected_port = ""
            self._apply_connection_state(False)

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
        def _run_script(link) -> tuple[list[str], bool]:
            out_lines: list[str] = []
            ok_all = True
            for ln, a, r, v in cmds:
                # Accept sentinel v == -999 for reads.
                if a < 0 or r < 0 or (v < 0 and v != -999):
                    out_lines.append(f"Line {ln}: parse error")
                    ok_all = False
                    continue
                if v == -999:
                    val = link.i2c_read(a, r)
                    if val is None:
                        out_lines.append(f"Line {ln}: r {a:#x} {r:#x} -> ERR")
                        ok_all = False
                    else:
                        out_lines.append(f"Line {ln}: r {a:#x} {r:#x} -> OK 0x{val:02X}")
                else:
                    ok = link.i2c_write(a, r, v)
                    out_lines.append(f"Line {ln}: w {a:#x} {r:#x} {v:#x} -> {'OK' if ok else 'ERR'}")
                    if not ok:
                        ok_all = False
            return out_lines, ok_all

        try:
            out_lines, ok_all = self._link_mgr.run(
                _run_script,
                port=self._connected_port,
                auto=False,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "I2C", f"Run failed:\n{e}")
            return

        for line in out_lines:
            self.output.appendPlainText(line)
        self.output.appendPlainText("Done: all OK" if ok_all else "Done: with errors")
