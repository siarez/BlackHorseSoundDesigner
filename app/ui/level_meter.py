from __future__ import annotations
import math
from PySide6 import QtWidgets, QtCore, QtGui


class _NotchedProgressBar(QtWidgets.QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_db = -80.0
        self._max_db = 0.0
        self._major_step_db = 10.0
        self._minor_step_db = 5.0

    def set_db_range(self, min_db: float, max_db: float):
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self.contentsRect().adjusted(2, 2, -2, -2)
        if rect.height() <= 0:
            return
        span = self._max_db - self._min_db
        if span <= 1e-6:
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)
        major_pen = QtGui.QPen(self.palette().mid().color())
        major_pen.setWidth(1)
        minor_color = self.palette().mid().color()
        minor_color.setAlpha(120)
        minor_pen = QtGui.QPen(minor_color)
        minor_pen.setWidth(1)

        # Minor ticks every 5 dB.
        db = self._min_db
        while db <= self._max_db + 1e-6:
            n = (db - self._min_db) / span
            y = rect.bottom() - int(n * rect.height())
            p.setPen(minor_pen)
            p.drawLine(rect.left(), y, rect.right(), y)
            db += self._minor_step_db

        # Major ticks every 10 dB.
        db = self._min_db
        while db <= self._max_db + 1e-6:
            n = (db - self._min_db) / span
            y = rect.bottom() - int(n * rect.height())
            p.setPen(major_pen)
            p.drawLine(rect.left(), y, rect.right(), y)
            db += self._major_step_db


class _ScaleCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_db = -80.0
        self._max_db = 0.0
        self._major_step_db = 10.0
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.setMinimumWidth(34)

    def set_db_range(self, min_db: float, max_db: float):
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self.contentsRect().adjusted(0, 2, 0, -2)
        if rect.height() <= 0:
            return
        span = self._max_db - self._min_db
        if span <= 1e-6:
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        p.setPen(self.palette().mid().color())
        fm = p.fontMetrics()
        step = self._major_step_db
        start = math.ceil(self._min_db / step) * step
        db = start
        while db <= self._max_db + 1e-6:
            # Skip endpoints to avoid clipping against top/bottom margins.
            if abs(db - self._min_db) < 1e-6 or abs(db - self._max_db) < 1e-6:
                db += step
                continue
            n = (db - self._min_db) / span
            y = rect.bottom() - int(n * rect.height())
            txt = f"{int(round(db))}"
            p.drawText(rect.left() + 2, y + (fm.ascent() // 2), txt)
            db += step


class _ScaleColumn(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.setSpacing(4)
        self.canvas = _ScaleCanvas(self)
        lay.addWidget(self.canvas, 1)
        # Spacer row to align with the channel index labels under each bar.
        spacer = QtWidgets.QLabel(" ", self)
        spacer.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        lay.addWidget(spacer, 0)

    def set_db_range(self, min_db: float, max_db: float):
        self.canvas.set_db_range(min_db, max_db)


class _VBar(QtWidgets.QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.bar = _NotchedProgressBar(self)
        self.bar.setOrientation(QtCore.Qt.Vertical)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(18)
        # Neutral base style; color is updated dynamically
        self._set_color('#3cb371')  # mediumseagreen
        lbl = QtWidgets.QLabel(title, self)
        lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        lay.addWidget(self.bar, 1)
        lay.addWidget(lbl, 0)

    def _set_color(self, color: str):
        self.bar.setStyleSheet(
            "QProgressBar { border: 1px solid palette(mid); background: palette(base); }\n"
            f"QProgressBar::chunk {{ background-color: {color}; }}"
        )

    def set_level(self, v01: float):
        v = int(max(0.0, min(1.0, float(v01))) * 1000)
        self.bar.setValue(v)
        # Simple color zones
        if v < 700:
            self._set_color('#3cb371')  # greenish
        elif v < 900:
            self._set_color('#f1c40f')  # yellow
        else:
            self._set_color('#e74c3c')  # red

    def set_level_with_db(self, v01: float, dbfs: float):
        v = int(max(0.0, min(1.0, float(v01))) * 1000)
        self.bar.setValue(v)
        db = float(dbfs)
        # Color zones are based on dBFS thresholds only.
        if db < -60.0:
            self._set_color('#202020')  # gray for very low levels
        elif db < -18.0:
            self._set_color('#3cb371')  # green
        elif db < -6.0:
            self._set_color('#f1c40f')  # yellow
        else:
            self._set_color('#e74c3c')  # red

    def set_value_text(self, text: str):
        # No-op: external widget shows numeric values in a shared row
        pass

    def set_db_range(self, min_db: float, max_db: float):
        self.bar.set_db_range(min_db, max_db)


class LevelMeterWidget(QtWidgets.QWidget):
    """Two vertical level meters (L/R) for ES9821 peak levels.

    Call set_levels(l, r) with values in [0,1].
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_db = -60.0
        self._max_db = 0.0
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Title
        title = QtWidgets.QLabel("Levels (dBFS)", self)
        title.setAlignment(QtCore.Qt.AlignHCenter)
        title.setStyleSheet("color: palette(mid);")
        root.addWidget(title)
        self.scale_lbl = QtWidgets.QLabel("", self)
        self.scale_lbl.setAlignment(QtCore.Qt.AlignHCenter)
        self.scale_lbl.setStyleSheet("color: palette(mid); font-size: 10px;")
        root.addWidget(self.scale_lbl)

        bars = QtWidgets.QHBoxLayout()
        bars.setSpacing(8)
        self.left_bar = _VBar("IN1", self)
        self.scale_col = _ScaleColumn(self)
        self.right_bar = _VBar("IN2", self)
        bars.addWidget(self.left_bar, 1)
        bars.addWidget(self.scale_col, 0)
        bars.addWidget(self.right_bar, 1)
        root.addLayout(bars, 1)

        # Raw value debug row under bars
        vals = QtWidgets.QHBoxLayout()
        vals.setSpacing(8)
        self.lbl_val_l = QtWidgets.QLabel("0", self)
        self.lbl_val_r = QtWidgets.QLabel("0", self)
        for w in (self.lbl_val_l, self.lbl_val_r):
            w.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
            w.setStyleSheet("color: palette(mid); font-size: 9px;")
        vals.addWidget(self.lbl_val_l, 1)
        vals.addWidget(self.lbl_val_r, 1)
        root.addLayout(vals)

        # Status hint (optional)
        self.hint = QtWidgets.QLabel("", self)
        self.hint.setAlignment(QtCore.Qt.AlignHCenter)
        self.hint.setStyleSheet("color: palette(mid); font-size: 10px;")
        root.addWidget(self.hint)
        self.set_scale_db(self._min_db, self._max_db)

    def set_levels(self, left01: float, right01: float):
        self.left_bar.set_level(left01)
        self.right_bar.set_level(right01)

    def set_hint(self, text: str):
        self.hint.setText(text)

    def set_values_text(self, left_text: str, right_text: str):
        self.left_bar.set_value_text(left_text)
        self.right_bar.set_value_text(right_text)
        self.lbl_val_l.setText(str(left_text))
        self.lbl_val_r.setText(str(right_text))

    def set_scale_db(self, min_db: float, max_db: float):
        self._min_db = float(min_db)
        self._max_db = float(max_db)
        self.scale_lbl.setText(f"{self._min_db:.0f} .. {self._max_db:.1f} dBFS")
        self.left_bar.set_db_range(self._min_db, self._max_db)
        self.scale_col.set_db_range(self._min_db, self._max_db)
        self.right_bar.set_db_range(self._min_db, self._max_db)

    def set_levels_db(self, left_db: float, right_db: float):
        span = max(1e-6, self._max_db - self._min_db)
        l01 = (float(left_db) - self._min_db) / span
        r01 = (float(right_db) - self._min_db) / span
        self.left_bar.set_level_with_db(l01, left_db)
        self.right_bar.set_level_with_db(r01, right_db)
