from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui

from .util import q_to_hex_twos, notify
from ..device_interface.cdc_link import CdcLink, auto_detect_port
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

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: hex readout
        left = QtWidgets.QWidget()
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
        vleft.addStretch(1)
        vleft.addWidget(self.btn_send)
        root.addWidget(right, 1)

        self._refresh_hex()

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

        port = auto_detect_port()
        if not port:
            QtWidgets.QMessageBox.warning(self, 'Mix/Gain', 'No device found (auto-detect failed)')
            return
        try:
            link = CdcLink(port)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Mix/Gain', f'Failed to open {port}: {e}')
            return

        try:
            payload = bytearray()
            payload.append(0x4A)
            cur_page = None
            for page_i, sub_i, val_u32 in items:
                if page_i != cur_page:
                    payload.append(0xFD); payload.append(page_i & 0xFF)
                    cur_page = page_i
                payload.append(0x80 | (sub_i & 0x7F))
                payload.append((val_u32 >> 24) & 0xFF)
                payload.append((val_u32 >> 16) & 0xFF)
                payload.append((val_u32 >> 8) & 0xFF)
                payload.append(val_u32 & 0xFF)
            # Dedicated record id for MIX/GAIN ADJUST
            ok, lines = link.jwrb_with_log(TYPE_COEFF, REC_MIX_GAIN, bytes(payload))
            if ok:
                applies = [ln for ln in lines if ln.startswith('OK APPLY') or ln.startswith('ERR APPLY')]
                msg = 'Mix/Gain Adjust saved + applied'
                if applies:
                    msg += " — " + " | ".join(applies)
                notify(self, msg)
            else:
                QtWidgets.QMessageBox.warning(self, 'Mix/Gain', 'Journal write failed')
            # Sidecar
            try:
                order = list(self.NAMES.keys())
                side = pack_q97_values(order, self.to_state_dict())
                _ok2, _ = link.jwrb_with_log(TYPE_APP_STATE, REC_STATE_MIXGAIN, side)
            except Exception:
                pass
        finally:
            try:
                link.close()
            except Exception:
                pass
