from __future__ import annotations

from PySide6 import QtWidgets, QtCore

from ..device_interface.cdc_link import auto_detect_port, list_serial_ports
from ..device_interface.device_link_manager import get_device_link_manager


class JournalTab(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._link_mgr = get_device_link_manager()
        self._connected_port: str = ""

        # Top row: port selection and controls
        self.port_combo = QtWidgets.QComboBox(self)
        self.refresh_btn = QtWidgets.QPushButton("Refresh", self)
        self.auto_btn = QtWidgets.QPushButton("Auto-Detect", self)
        self.connect_btn = QtWidgets.QPushButton("Connect", self)
        self.readlog_btn = QtWidgets.QPushButton("Read Device Log", self)
        self.status_lbl = QtWidgets.QLabel("Disconnected", self)
        self.hint_lbl = QtWidgets.QLabel("I2C uses 7-bit addresses. ES9821 default: 0x20 (8-bit write 0x40)", self)
        self.hint_lbl.setStyleSheet("color: gray; font-size: 11px;")

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:"))
        top.addWidget(self.port_combo, 1)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.auto_btn)
        top.addWidget(self.connect_btn)
        top.addWidget(self.readlog_btn)
        top.addWidget(self.status_lbl)

        # Middle row: type/id inputs and actions
        self.type_edit = QtWidgets.QLineEdit(self)
        self.type_edit.setPlaceholderText("0x21")
        self.id_edit = QtWidgets.QLineEdit(self)
        self.id_edit.setPlaceholderText("0x00")
        self.jrd_btn = QtWidgets.QPushButton("Read (hex)", self)
        self.jrdb_btn = QtWidgets.QPushButton("Read (raw)", self)

        mid = QtWidgets.QHBoxLayout()
        mid.addWidget(QtWidgets.QLabel("Type:"))
        mid.addWidget(self.type_edit)
        mid.addSpacing(10)
        mid.addWidget(QtWidgets.QLabel("ID:"))
        mid.addWidget(self.id_edit)
        mid.addSpacing(20)
        mid.addWidget(self.jrd_btn)
        mid.addWidget(self.jrdb_btn)
        mid.addStretch(1)

        # Output area
        self.output = QtWidgets.QPlainTextEdit(self)
        self.output.setReadOnly(True)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.hint_lbl)
        root.addLayout(mid)
        root.addWidget(self.output, 1)

        # Wire signals
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.auto_btn.clicked.connect(self._on_auto)
        self.connect_btn.clicked.connect(self._on_connect)
        self.jrd_btn.clicked.connect(self._on_jrd)
        self.jrdb_btn.clicked.connect(self._on_jrdb)
        self.readlog_btn.clicked.connect(self._on_readlog)

        # Initial
        self._on_refresh()
        self._apply_connection_state(False)

    # --------------- Helpers ---------------
    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _apply_connection_state(self, connected: bool, port: str = "", status_text: str = ""):
        self.connect_btn.setText("Disconnect" if connected else "Connect")
        self.port_combo.setEnabled(not connected)
        self.refresh_btn.setEnabled(not connected)
        self.auto_btn.setEnabled(not connected)
        if status_text:
            self._set_status(status_text)
        elif connected:
            self._set_status(f"Connected: {port}")
        else:
            self._set_status("Disconnected")

    def _ensure_link(self) -> bool:
        if self._connected_port:
            return True
        port = self._current_port()
        if not port:
            QtWidgets.QMessageBox.warning(self, "Device", "Please select a serial port.")
            return False
        try:
            self._connected_port = self._link_mgr.connect(port=port, auto=False)
            ok = self._link_mgr.run(lambda link: link.init(), port=self._connected_port, auto=False)
            if not ok:
                self._apply_connection_state(True, self._connected_port, f"Connected: {self._connected_port} (init failed)")
            else:
                self._apply_connection_state(True, self._connected_port)
            return True
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Connect", f"Failed to open {port}:\n{e}")
            self._connected_port = ""
            self._apply_connection_state(False)
            return False

    def _close_link(self):
        if self._connected_port:
            try:
                self._link_mgr.disconnect()
            except Exception:
                pass
            self._connected_port = ""
        self._apply_connection_state(False)

    def _current_port(self) -> str:
        idx = self.port_combo.currentIndex()
        if idx < 0:
            return ""
        return self.port_combo.itemData(idx) or ""

    def _parse_type_id(self) -> tuple[int, int] | None:
        t_text = self.type_edit.text().strip() or "0x21"
        i_text = self.id_edit.text().strip() or "0x00"
        try:
            typ = int(t_text, 0)
            _id = int(i_text, 0)
        except Exception:
            QtWidgets.QMessageBox.warning(self, "Journal", "Type/ID must be integers (e.g., 0x21, 0x00)")
            return None
        if not (0 <= typ <= 255 and 0 <= _id <= 255):
            QtWidgets.QMessageBox.warning(self, "Journal", "Type/ID must be 0..255")
            return None
        return typ, _id

    def _populate_ports(self, auto_select: bool = False):
        ports = list_serial_ports()
        sel_index = -1
        self.port_combo.clear()
        for p in ports:
            label = f"{p.get('device','')} — {p.get('product','') or p.get('description','')} ({p.get('manufacturer','')})"
            self.port_combo.addItem(label, p.get('device',''))
        if auto_select:
            dev = auto_detect_port()
            if dev:
                for i in range(self.port_combo.count()):
                    if self.port_combo.itemData(i) == dev:
                        sel_index = i
                        break
        if sel_index >= 0:
            self.port_combo.setCurrentIndex(sel_index)

    # --------------- Slots ---------------
    def _on_refresh(self):
        self._populate_ports(auto_select=False)

    def _on_auto(self):
        self._populate_ports(auto_select=True)

    def _on_connect(self):
        if not self._connected_port:
            self._ensure_link()
        else:
            self._close_link()

    def _on_jrd(self):
        if not self._ensure_link():
            return
        ti = self._parse_type_id()
        if not ti:
            return
        typ, _id = ti
        try:
            data = self._link_mgr.run(
                lambda link: link.jrd(typ, _id),
                port=self._connected_port,
                auto=False,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Journal", f"Read failed:\n{e}")
            return
        if data is None:
            self.output.setPlainText("ERR JNF (no record)")
            return
        self._display_bytes(data, note="JRD")

    def _on_jrdb(self):
        if not self._ensure_link():
            return
        ti = self._parse_type_id()
        if not ti:
            return
        typ, _id = ti
        try:
            data = self._link_mgr.run(
                lambda link: link.jrdb(typ, _id),
                port=self._connected_port,
                auto=False,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Journal", f"Read failed:\n{e}")
            return
        if data is None:
            self.output.setPlainText("ERR JNF (no record)")
            return
        self._display_bytes(data, note="JRDB")

    def _on_readlog(self):
        if not self._ensure_link():
            return
        try:
            lines = self._link_mgr.run(
                lambda link: link.read_lines(1.0),
                port=self._connected_port,
                auto=False,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Journal", f"Read log failed:\n{e}")
            return
        if not lines:
            self.output.appendPlainText("[log] (no lines)\n")
            return
        for ln in lines:
            self.output.appendPlainText(f"[log] {ln}")

    def _display_bytes(self, data: bytes, note: str = ""):
        # Render as hex, grouped binary with offsets, and ASCII preview
        hex_str = " ".join(f"{b:02X}" for b in data)

        # Binary view: one byte per line with byte index (offset)
        bin_lines = [f"{i:04X}: {b:08b}" for i, b in enumerate(data)]
        bin_block = "\n".join(bin_lines)

        ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data)
        self.output.setPlainText(
            f"{note}: {len(data)} bytes\n\nHex:\n{hex_str}\n\nBinary (1/line with index):\n{bin_block}\n\nASCII:\n{ascii_str}\n"
        )
