from __future__ import annotations
from PySide6 import QtWidgets, QtCore, QtGui
import math

from .util import mk_dspin, q_to_hex_twos


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

        # Match other tabs: left readout, right controls
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Left: hex readout
        left = QtWidgets.QWidget()
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
        vright.addStretch(1)
        root.addWidget(right, 1)

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
