from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui
import math

from .util import mk_dspin, q_to_hex_twos, notify, LEFT_SIDEBAR_WIDTH
from .device_target_selector import DeviceTargetSelector
from ..device_interface.device_write_manager import (
    JournalWrite,
    build_i2c32_payload,
    get_device_write_manager,
)
from ..device_interface.record_ids import TYPE_COEFF, TYPE_APP_STATE, REC_INPUT_MIXER, REC_STATE_MIXER
from ..device_interface.state_sidecar import pack_q97_values
from pathlib import Path
import json as _json


class InputMixerTab(QtWidgets.QWidget):
    """UI for INPUT MIXER coefficients (Left/Right mix) in Q9.23.

    Registers:
      - 1-to-A   (A_out from In1)
      - 2-to-A  (A_out from In2)
      - 1-to-B  (B_out from In1)
      - 2-to-B (B_out from In2)
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._writer = get_device_write_manager()
        self._target_devices: list[dict[str, str]] = []

        # Match other tabs: left readout, right controls
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: hex readout
        left = QtWidgets.QWidget()
        left.setFixedWidth(LEFT_SIDEBAR_WIDTH)
        vleft = QtWidgets.QVBoxLayout(left)
        vleft.setContentsMargins(0, 0, 0, 0)
        vleft.setSpacing(6)

        gb = QtWidgets.QGroupBox("INPUT MIXER Coeffs (Q9.23 two's complement)")
        v = QtWidgets.QVBoxLayout(gb)
        self.txt_hex = QtWidgets.QPlainTextEdit()
        self.txt_hex.setReadOnly(True)
        self.txt_hex.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        self.txt_hex.setFont(font)
        v.addWidget(self.txt_hex)
        vleft.addWidget(gb)

        root.addWidget(left, 0)

        # Right: controls
        right = QtWidgets.QWidget()
        vright = QtWidgets.QVBoxLayout(right)
        vright.setContentsMargins(0, 0, 0, 0)
        vright.setSpacing(8)

        # Brief help text (rich text so we can control line height)
        help_html = (
            "<div style='line-height: 140%;'>"
            "Set the 2×2 mix matrix in signed Q9.23 (≈ −256 to +255.999999).<br>"
            "Identity mix: In1‑to‑A = 1.0, In2‑to‑B = 1.0, others = 0.0.<br>"
            "A out = (In1 × In1‑to‑A) + (In2 × In2‑to‑A)<br>"
            "B out = (In1 × In1‑to‑B) + (In2 × In2‑to‑B)"
            "</div>"
        )
        help_lbl = QtWidgets.QLabel(help_html)
        help_lbl.setTextFormat(QtCore.Qt.RichText)
        help_lbl.setWordWrap(True)
        # Bump font slightly for readability
        f = help_lbl.font()
        if f.pointSize() > 0:
            f.setPointSize(f.pointSize() + 2)
        else:
            f.setPixelSize(14)
        help_lbl.setFont(f)
        # Add a subtle border and padding that adapts to palette
        help_lbl.setStyleSheet(
            "QLabel {"
            "  border: 1px solid palette(mid);"
            "  border-radius: 4px;"
            "  padding: 6px;"
            "}"
        )
        vright.addWidget(help_lbl)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        vright.addLayout(grid)

        # Spinboxes (Q9.23), range ~[-256, 256)
        def spin(default: float):
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-256.0, 255.999999)
            s.setDecimals(6)
            s.setSingleStep(0.01)
            s.setValue(default)
            s.valueChanged.connect(self._refresh_hex)
            return s

        row = 0
        grid.addWidget(QtWidgets.QLabel("A_out = In1 ×"), row, 0)
        self.spin_In1_to_A = spin(1.0)
        grid.addWidget(self.spin_In1_to_A, row, 1)
        grid.addWidget(QtWidgets.QLabel("+ In2 ×"), row, 2)
        self.spin_In2_to_A = spin(1.0)
        grid.addWidget(self.spin_In2_to_A, row, 3)

        row += 1
        grid.addWidget(QtWidgets.QLabel("B_out = In1 ×"), row, 0)
        self.spin_In1_to_B = spin(1.0)
        grid.addWidget(self.spin_In1_to_B, row, 1)
        grid.addWidget(QtWidgets.QLabel("+ In2 ×"), row, 2)
        self.spin_In2_to_B = spin(1.0)
        grid.addWidget(self.spin_In2_to_B, row, 3)

        # dB matrix below controls
        db_group = QtWidgets.QGroupBox("Effective Gains (dB)")
        db_grid = QtWidgets.QGridLayout(db_group)
        db_grid.setHorizontalSpacing(12)
        db_grid.setVerticalSpacing(6)
        # headers
        db_grid.addWidget(QtWidgets.QLabel(""), 0, 0)
        db_grid.addWidget(QtWidgets.QLabel("In1"), 0, 1)
        db_grid.addWidget(QtWidgets.QLabel("In2"), 0, 2)
        # row labels
        db_grid.addWidget(QtWidgets.QLabel("A_out"), 1, 0)
        db_grid.addWidget(QtWidgets.QLabel("B_out"), 2, 0)
        # value labels
        self.lbl_db_LtoL = QtWidgets.QLabel("")
        self.lbl_db_RtoL = QtWidgets.QLabel("")
        self.lbl_db_LtoR = QtWidgets.QLabel("")
        self.lbl_db_RtoR = QtWidgets.QLabel("")
        db_grid.addWidget(self.lbl_db_LtoL, 1, 1)
        db_grid.addWidget(self.lbl_db_RtoL, 1, 2)
        db_grid.addWidget(self.lbl_db_LtoR, 2, 1)
        db_grid.addWidget(self.lbl_db_RtoR, 2, 2)
        vright.addWidget(db_group)

        # Spacer to push grid up
        # Send button at bottom-left panel for consistency
        self.btn_send = QtWidgets.QPushButton("Send Input Mixer to Device")
        self.btn_send.setToolTip("Send INPUT MIXER (Q9.23) to TAS3251 via journal")
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
        return {
            'LefttoLeft': float(self.spin_In1_to_A.value()),
            'RighttoLeft': float(self.spin_In2_to_A.value()),
            'LefttoRight': float(self.spin_In1_to_B.value()),
            'RighttoRight': float(self.spin_In2_to_B.value()),
        }

    def apply_state_dict(self, d: dict | None):
        if not d:
            return
        def _set(name: str, spin: QtWidgets.QDoubleSpinBox):
            if name in d and spin is not None:
                try:
                    spin.setValue(float(d[name]))
                except Exception:
                    pass
        _set('LefttoLeft', self.spin_In1_to_A)
        _set('RighttoLeft', self.spin_In2_to_A)
        _set('LefttoRight', self.spin_In1_to_B)
        _set('RighttoRight', self.spin_In2_to_B)
        self._refresh_hex()

    def _q923_hex(self, v: float) -> str:
        # 9.23 signed => 23 fractional bits
        return q_to_hex_twos(float(v), 23)

    def _refresh_hex(self):
        lines = []
        lines.append(f"In1 to A   = {self.spin_In1_to_A.value():.6f}  ->  {self._q923_hex(self.spin_In1_to_A.value())}")
        lines.append(f"In2 to A  = {self.spin_In2_to_A.value():.6f}  ->  {self._q923_hex(self.spin_In2_to_A.value())}")
        lines.append(f"In1 to B  = {self.spin_In1_to_B.value():.6f}  ->  {self._q923_hex(self.spin_In1_to_B.value())}")
        lines.append(f"In2 to B = {self.spin_In2_to_B.value():.6f}  ->  {self._q923_hex(self.spin_In2_to_B.value())}")
        self.txt_hex.setPlainText("\n".join(lines))

        # Update dB labels (20*log10(|gain|); show −∞ for 0, mark inversion on negative gains)
        def fmt_db(v: float) -> str:
            if v == 0.0:
                return "−∞ dB"
            db = 20.0 * math.log10(abs(v))
            inv = " (inv)" if v < 0.0 else ""
            return f"{db:.2f} dB{inv}"

        self.lbl_db_LtoL.setText(fmt_db(self.spin_In1_to_A.value()))
        self.lbl_db_RtoL.setText(fmt_db(self.spin_In2_to_A.value()))
        self.lbl_db_LtoR.setText(fmt_db(self.spin_In1_to_B.value()))
        self.lbl_db_RtoR.setText(fmt_db(self.spin_In2_to_B.value()))

    def values_hex(self) -> dict[str, str]:
        """Return mapping of INPUT MIXER names -> hex string in Q9.23."""
        return {
            'LefttoLeft': self._q923_hex(self.spin_In1_to_A.value()),
            'RighttoLeft': self._q923_hex(self.spin_In2_to_A.value()),
            'LefttoRight': self._q923_hex(self.spin_In1_to_B.value()),
            'RighttoRight': self._q923_hex(self.spin_In2_to_B.value()),
        }

    def _on_send(self):
        # Load INPUT MIXER map rows
        ref_path = (Path(__file__).resolve().parents[2] / 'app/eqcore/maps/shabrang_tas3251.jsonl')
        try:
            lines = ref_path.read_text(encoding='utf-8').splitlines()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Input Mixer', f'Failed to read reference map: {e}')
            return

        targets = self.values_hex()
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
            if current != 'INPUT MIXER':
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
            QtWidgets.QMessageBox.warning(self, 'Input Mixer', 'No INPUT MIXER map entries found to send')
            return

        writes = [
            JournalWrite(
                typ=TYPE_COEFF,
                rec_id=REC_INPUT_MIXER,
                payload=build_i2c32_payload(items),
                label="INPUT MIXER",
            )
        ]
        try:
            order = ['LefttoLeft', 'RighttoLeft', 'LefttoRight', 'RighttoRight']
            side = pack_q97_values(order, self.to_state_dict())
            writes.append(JournalWrite(TYPE_APP_STATE, REC_STATE_MIXER, side, "STATE MIXER"))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Input Mixer', f'Failed to build mixer sidecar: {e}')
            return

        ports = self._selected_ports()
        try:
            res = self._writer.apply(writes, ports=ports, auto=not bool(ports))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Input Mixer', f'Failed to write device: {e}')
            return

        if res.ok:
            msg = 'Input Mixer saved + applied'
            if res.apply_logs:
                msg += " — " + " | ".join(res.apply_logs)
            notify(self, msg)
        else:
            QtWidgets.QMessageBox.warning(self, 'Input Mixer', f'Journal write failed: {", ".join(res.failed)}')
