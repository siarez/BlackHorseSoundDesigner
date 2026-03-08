from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui

from .util import q_to_hex_twos, notify, LEFT_SIDEBAR_WIDTH
from .device_target_selector import DeviceTargetSelector
from ..device_interface.device_write_manager import (
    JournalWrite,
    build_i2c32_payload,
    get_device_write_manager,
)
from ..device_interface.record_ids import TYPE_COEFF, TYPE_APP_STATE, REC_MIX_GAIN, REC_STATE_MIXGAIN
from ..device_interface.state_sidecar import pack_q97_values
from pathlib import Path
import json as _json


class MixGainAdjustTab(QtWidgets.QWidget):
    """UI for MIX/GAIN ADJUST (Q9.23) registers.

    Section entries (from map):
      - LefttoSub, RighttoSub, SubMixScratchL, SubMixScratchR,
        BassMonoLeft, BassMonoRight, BassMonoSub
    """

    # Name -> default linear value (Q9.23)
    NAMES: dict[str, float] = {
        "LefttoSub": 0.0,
        "RighttoSub": 0.0,
        "SubMixScratchL": 1.0,
        "SubMixScratchR": 0.0,
        "BassMonoLeft": 1.0,
        "BassMonoRight": 0.0,
        "BassMonoSub": 0.0,
    }

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._writer = get_device_write_manager()
        self._target_devices: list[dict[str, str]] = []

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: hex readout
        left = QtWidgets.QWidget()
        left.setFixedWidth(LEFT_SIDEBAR_WIDTH)
        vleft = QtWidgets.QVBoxLayout(left)
        vleft.setContentsMargins(0, 0, 0, 0)
        vleft.setSpacing(6)
        gb = QtWidgets.QGroupBox("MIX/GAIN ADJUST (Q9.23 two's complement)")
        v = QtWidgets.QVBoxLayout(gb)
        self.txt_hex = QtWidgets.QPlainTextEdit()
        self.txt_hex.setReadOnly(True)
        self.txt_hex.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.txt_hex.setFont(font)
        v.addWidget(self.txt_hex)
        vleft.addWidget(gb)
        root.addWidget(left, 0)

        # Right: controls grid
        right = QtWidgets.QWidget()
        vright = QtWidgets.QVBoxLayout(right)
        vright.setContentsMargins(0, 0, 0, 0)
        vright.setSpacing(8)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        vright.addLayout(grid)

        self._spins: dict[str, QtWidgets.QDoubleSpinBox] = {}

        def spin(default: float) -> QtWidgets.QDoubleSpinBox:
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-256.0, 255.999999)
            s.setDecimals(6)
            s.setSingleStep(0.01)
            s.setValue(default)
            s.valueChanged.connect(self._refresh_hex)
            return s

        row = 0
        for name, default in self.NAMES.items():
            grid.addWidget(QtWidgets.QLabel(name + ":"), row, 0)
            s = spin(float(default))
            self._spins[name] = s
            grid.addWidget(s, row, 1)
            row += 1

        # Send button at bottom-left for consistency
        self.btn_send = QtWidgets.QPushButton("Send Mix/Gain Adjust to Device")
        self.btn_send.setToolTip("Send MIX/GAIN ADJUST (Q9.23) to TAS3251 via journal")
        self.btn_send.clicked.connect(self._on_send)
        self.target_selector = DeviceTargetSelector(self)
        self.target_selector.selectionChanged.connect(self._update_send_enabled)
        vleft.addStretch(1)
        vleft.addWidget(self.target_selector)
        vleft.addWidget(self.btn_send)
        root.addWidget(right, 1)

        self._refresh_hex()
        self._update_send_enabled()

    def set_target_devices(self, devices: list[dict[str, str]]):
        self._target_devices = [dict(d) for d in (devices or [])]
        self.target_selector.set_devices(self._target_devices)
        self._update_send_enabled()

    def _selected_ports(self) -> list[str]:
        if not self.target_selector.isVisible():
            return []
        by_uid = {str(d.get("uid", "")).upper(): str(d.get("port", "")) for d in self._target_devices}
        out: list[str] = []
        for uid in self.target_selector.selected_uids():
            p = by_uid.get(uid.upper(), "")
            if p:
                out.append(p)
        return out

    def _update_send_enabled(self):
        if not self._target_devices:
            self.btn_send.setEnabled(False)
        elif self.target_selector.isVisible():
            self.btn_send.setEnabled(self.target_selector.has_selection())
        else:
            self.btn_send.setEnabled(True)

    # ---------------- State (Save/Load) ----------------
    def to_state_dict(self) -> dict:
        return {name: float(self._spins[name].value()) for name in self.NAMES.keys()}

    def apply_state_dict(self, d: dict | None):
        if not d:
            return
        for name, spin in self._spins.items():
            if name in d:
                try:
                    spin.setValue(float(d[name]))
                except Exception:
                    pass
        self._refresh_hex()

    def _q923_hex(self, v: float) -> str:
        return q_to_hex_twos(float(v), 23)

    def _refresh_hex(self):
        lines = []
        for name in self.NAMES.keys():
            val = self._spins[name].value()
            lines.append(f"{name:>14} = {val:.6f}  ->  {self._q923_hex(val)}")
        self.txt_hex.setPlainText("\n".join(lines))

    def _on_send(self):
        # Load map and collect MIX/GAIN ADJUST rows
        ref_path = (Path(__file__).resolve().parents[2] / 'app/eqcore/maps/shabrang_tas3251.jsonl')
        try:
            lines = ref_path.read_text(encoding='utf-8').splitlines()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Mix/Gain', f'Failed to read reference map: {e}')
            return

        targets = {name: self._q923_hex(self._spins[name].value()) for name in self.NAMES.keys()}
        items: list[tuple[int,int,int]] = []
        current = ''
        for ln in lines:
            s = ln.strip()
            if not s:
                continue
            if s.startswith('{') and '"type": "section"' in s:
                try:
                    o = _json.loads(s)
                    current = o.get('title', current)
                except Exception:
                    pass
                continue
            if current != 'MIX/GAIN ADJUST':
                continue
            try:
                o = _json.loads(s)
            except Exception:
                continue
            name = o.get('name','')
            if name not in targets:
                continue
            page = o.get('page'); sub = o.get('subaddr')
            if not (page and sub):
                continue
            try:
                page_i = int(page, 0); sub_i = int(sub, 0)
                val_u32 = int(targets[name], 16)
            except Exception:
                continue
            items.append((page_i, sub_i, val_u32))

        if not items:
            QtWidgets.QMessageBox.warning(self, 'Mix/Gain', 'No MIX/GAIN ADJUST map entries found to send')
            return

        writes = [
            JournalWrite(
                typ=TYPE_COEFF,
                rec_id=REC_MIX_GAIN,
                payload=build_i2c32_payload(items),
                label="MIX/GAIN ADJUST",
            )
        ]
        try:
            order = list(self.NAMES.keys())
            side = pack_q97_values(order, self.to_state_dict())
            writes.append(JournalWrite(TYPE_APP_STATE, REC_STATE_MIXGAIN, side, "STATE MIX/GAIN"))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Mix/Gain', f'Failed to build mix/gain sidecar: {e}')
            return

        ports = self._selected_ports()
        try:
            res = self._writer.apply(writes, ports=ports, auto=not bool(ports))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Mix/Gain', f'Failed to write device: {e}')
            return

        if res.ok:
            msg = 'Mix/Gain Adjust saved + applied'
            if res.apply_logs:
                msg += " — " + " | ".join(res.apply_logs)
            notify(self, msg)
        else:
            QtWidgets.QMessageBox.warning(self, 'Mix/Gain', f'Journal write failed: {", ".join(res.failed)}')
