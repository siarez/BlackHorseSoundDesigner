from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui

from .util import q_to_hex_twos, notify
from ..device_interface.device_write_manager import (
    JournalWrite,
    build_i2c32_payload,
    get_device_write_manager,
)
from ..device_interface.record_ids import TYPE_COEFF, TYPE_APP_STATE, REC_OUT_GAINS_DIG, REC_STATE_XBAR
from ..device_interface.state_sidecar import pack_q97_values
from pathlib import Path
import json as _json


class OutputCrossbarTab(QtWidgets.QWidget):
    """UI for digital OUTPUT CROSS BAR gains (Q9.23)."""

    NAMES = [
        # Digital outputs
        "DigitalLeftfromLeft",
        "DigitalLeftfromRight",
        "DigitalLeftfromSub",
        "DigitalRightfromLeft",
        "DigitalRightfromRight",
        "DigitalRightfromSub",
    ]

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._writer = get_device_write_manager()

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: hex readout
        left = QtWidgets.QWidget()
        vleft = QtWidgets.QVBoxLayout(left)
        vleft.setContentsMargins(0, 0, 0, 0)
        vleft.setSpacing(6)
        gb = QtWidgets.QGroupBox("OUTPUT CROSS BAR Digital (Q9.23 two's complement)")
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

        # Defaults: L->L and R->R are 1.0; others 0.0
        defaults = {
            "DigitalLeftfromLeft": 1.0,
            "DigitalLeftfromRight": 0.0,
            "DigitalLeftfromSub": 0.0,
            "DigitalRightfromLeft": 0.0,
            "DigitalRightfromRight": 1.0,
            "DigitalRightfromSub": 0.0,
        }

        row = 0
        for name in self.NAMES:
            grid.addWidget(QtWidgets.QLabel(name + ":"), row, 0)
            s = spin(defaults.get(name, 0.0))
            self._spins[name] = s
            grid.addWidget(s, row, 1)
            row += 1

        # Send button at bottom-left for consistency
        self.btn_send = QtWidgets.QPushButton("Send Digital Output Cross Bar to Device")
        self.btn_send.setToolTip("Send digital OUTPUT CROSS BAR routes (Q9.23) to TAS3251 via journal")
        self.btn_send.clicked.connect(self._on_send)
        vleft.addStretch(1)
        vleft.addWidget(self.btn_send)
        root.addWidget(right, 1)

        self._refresh_hex()

    # ---------------- State (Save/Load) ----------------
    def to_state_dict(self) -> dict:
        return {name: float(self._spins[name].value()) for name in self.NAMES}

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
        for name in self.NAMES:
            val = self._spins[name].value()
            lines.append(f"{name:>20} = {val:.6f}  ->  {self._q923_hex(val)}")
        self.txt_hex.setPlainText("\n".join(lines))

    def _on_send(self):
        ref_path = (Path(__file__).resolve().parents[2] / 'app/eqcore/maps/shabrang_tas3251.jsonl')
        try:
            lines = ref_path.read_text(encoding='utf-8').splitlines()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Output Cross Bar', f'Failed to read reference map: {e}')
            return

        targets = {name: self._q923_hex(self._spins[name].value()) for name in self.NAMES}
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
            if current != 'OUTPUT CROSS BAR':
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
            QtWidgets.QMessageBox.warning(self, 'Output Cross Bar', 'No OUTPUT CROSS BAR map entries found to send')
            return

        writes = [
            JournalWrite(
                typ=TYPE_COEFF,
                rec_id=REC_OUT_GAINS_DIG,
                payload=build_i2c32_payload(items),
                label="OUTPUT CROSS BAR DIGITAL",
            )
        ]
        try:
            order = list(self.NAMES)
            side = pack_q97_values(order, self.to_state_dict())
            writes.append(JournalWrite(TYPE_APP_STATE, REC_STATE_XBAR, side, "STATE XBAR"))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Output Cross Bar', f'Failed to build xbar sidecar: {e}')
            return

        try:
            res = self._writer.apply(writes, auto=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Output Cross Bar', f'Failed to write device: {e}')
            return

        if res.ok:
            msg = 'Output Cross Bar saved + applied'
            if res.apply_logs:
                msg += " — " + " | ".join(res.apply_logs)
            notify(self, msg)
        else:
            QtWidgets.QMessageBox.warning(self, 'Output Cross Bar', f'Journal write failed: {", ".join(res.failed)}')
