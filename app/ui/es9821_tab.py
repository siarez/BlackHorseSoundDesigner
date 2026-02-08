from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict

from PySide6 import QtWidgets

from ..device_interface.cdc_link import auto_detect_port, list_serial_ports
from ..device_interface.device_link_manager import get_device_link_manager


class Es9821Tab(QtWidgets.QWidget):
    def __init__(self, parent=None, mapping_path: Path | None = None):
        super().__init__(parent)
        self._link_mgr = get_device_link_manager()
        self._connected_port: str = ""
        self._map_path = mapping_path or Path("app/eqcore/maps/shabrang_es9821.jsonl")

        self.port_combo = QtWidgets.QComboBox(self)
        self.refresh_btn = QtWidgets.QPushButton("Refresh", self)
        self.auto_btn = QtWidgets.QPushButton("Auto-Detect", self)
        self.connect_btn = QtWidgets.QPushButton("Connect", self)
        self.read_btn = QtWidgets.QPushButton("Read All", self)
        self.diff_only = QtWidgets.QCheckBox("Show only diffs", self)
        self.status_lbl = QtWidgets.QLabel("Disconnected", self)
        self.output = QtWidgets.QPlainTextEdit(self)
        self.output.setReadOnly(True)
        # Do not wrap lines; show long JSONL entries horizontally
        self.output.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:"))
        top.addWidget(self.port_combo, 1)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.auto_btn)
        top.addWidget(self.connect_btn)
        top.addWidget(self.read_btn)
        top.addWidget(self.diff_only)
        top.addWidget(self.status_lbl)

        root = QtWidgets.QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.output, 1)

        self.refresh_btn.clicked.connect(self._on_refresh)
        self.auto_btn.clicked.connect(self._on_auto)
        self.connect_btn.clicked.connect(self._on_connect)
        self.read_btn.clicked.connect(self._on_read_all)

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
            self.port_combo.addItem(label, p.get('device',''))
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
            QtWidgets.QMessageBox.warning(self, "ES9821", "Select a serial port or use Auto-Detect.")
            return False
        dev = self.port_combo.itemData(idx) or self.port_combo.currentText()
        if not dev:
            QtWidgets.QMessageBox.warning(self, "ES9821", "Serial port is empty.")
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

    def _on_read_all(self):
        if not self._ensure_link():
            return
        mapping = self._load_mapping(self._map_path)
        if not mapping:
            QtWidgets.QMessageBox.warning(self, "ES9821", f"No mapping entries loaded from {self._map_path}")
            return
        def _read_all(link) -> List[str]:
            # Iterate registers in order.
            out_lines: List[str] = []
            out_lines.append('{"type": "meta", "device": "ES9821", "schema": "es-reg-map-minimal-v1", "source": "live", "fields": ["addr", "register num", "name", "value", "bits"]}')
            for ent in mapping:
                addr = ent.get("addr")
                regnum = ent.get("register num")
                name = ent.get("name", "")
                bits = ent.get("bits", [])
                baseline = ent.get("reset", None)
                try:
                    a = int(addr, 0) if isinstance(addr, str) else int(addr)
                except Exception:
                    continue
                val = link.esr(a)
                # Filter by baseline if requested.
                if self.diff_only.isChecked():
                    # If no baseline provided, skip (treat as not a diff).
                    if not baseline:
                        continue
                    if val is None:
                        show = True  # show errors as diffs
                    else:
                        show = self._is_diff_from_baseline(val, baseline)
                    if not show:
                        continue
                if val is None:
                    # Still include a line with value omitted.
                    line = {
                        "addr": f"0x{a:02X}",
                        "register num": regnum if isinstance(regnum, int) else ent.get("register num"),
                        "name": name,
                        "value": "ERR",
                        "bits": bits,
                    }
                else:
                    line = {
                        "addr": f"0x{a:02X}",
                        "register num": regnum if isinstance(regnum, int) else ent.get("register num"),
                        "name": name,
                        "value": f"0b{val:08b}",
                        "bits": bits,
                    }
                out_lines.append(json.dumps(line))
            return out_lines

        try:
            lines = self._link_mgr.run(
                _read_all,
                port=self._connected_port,
                auto=False,
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "ES9821", f"Read failed:\n{e}")
            return

        self.output.setPlainText("\n".join(lines))

    def _load_mapping(self, path: Path) -> List[Dict]:
        try:
            raw = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        out: List[Dict] = []
        for ln in raw:
            ln = ln.strip()
            if not ln or ln.startswith("//"):
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("type") == "meta":
                continue
            out.append(obj)
        return out

    def _is_diff_from_baseline(self, val: int, baseline) -> bool:
        """Compare current value against a baseline string.
        - If baseline is hex (e.g., 0x1A), compare exact byte.
        - If baseline is binary with x (e.g., 0b10xx0010), ignore x bits.
        - If baseline missing/unknown, treat as different.
        """
        if not baseline:
            # No baseline means we don't consider it a diff for filtering
            return False
        try:
            if isinstance(baseline, str) and baseline.startswith("0x"):
                exp = int(baseline, 0)
                return (val & 0xFF) != (exp & 0xFF)
            if isinstance(baseline, str) and baseline.startswith("0b"):
                bits = baseline[2:]
                if not bits:
                    return True
                # Build mask/expected
                mask = 0
                exp = 0
                # Align to 8 bits (pad left if shorter)
                bits = bits[-8:].rjust(8, 'x')
                for i, ch in enumerate(bits):
                    bitpos = 7 - i
                    if ch in ('0','1'):
                        mask |= (1 << bitpos)
                        if ch == '1':
                            exp |= (1 << bitpos)
                return ((val & mask) != (exp & mask))
            # Fallback: try parse int
            exp = int(str(baseline), 0)
            return (val & 0xFF) != (exp & 0xFF)
        except Exception:
            return True
