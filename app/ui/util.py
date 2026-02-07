from __future__ import annotations
from PySide6 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg
import math


def mk_dspin(lo, hi, val, step, suffix, decimals) -> QtWidgets.QDoubleSpinBox:
    s = QtWidgets.QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    if suffix:
        s.setSuffix(" " + suffix.strip())
    return s


def row_color(index: int):
    """Return a perceptually distinct QColor for a given index.

    Uses golden‑angle hue spacing in HSL space to maximize separation between
    consecutive colors. Alternates lightness slightly to add contrast for
    adjacent entries while keeping good readability on both light/dark Fusion
    palettes.
    """
    golden = 0.61803398875  # golden ratio conjugate
    # Start away from pure red to avoid clashing with error highlights
    h = (0.12 + index * golden) % 1.0  # hue in [0,1)
    s = 0.75
    l = 0.55 if (index % 2 == 0) else 0.47
    return QtGui.QColor.fromHslF(h, s, l)


def build_plot(name_cascade: str):
    pg.setConfigOptions(antialias=True)
    # Use a custom log-axis that only shows 0.2, 0.4, 0.6, 0.8 minor ticks
    pw = pg.PlotWidget(axisItems={'bottom': _LogMinorAxis(orientation='bottom')})
    pw.setBackground("default")
    pw.setLogMode(x=True, y=False)
    pw.showGrid(x=True, y=True, alpha=0.3)
    pw.setLabel("bottom", "Frequency", units="Hz")
    pw.setLabel("left", "Magnitude", units="dB")
    pw.addLegend(offset=(10, 10))
    curve = pw.plot([], [], pen=pg.mkPen(width=2), name=name_cascade)
    pw.setYRange(-24, 24, padding=0.05)
    try:
        _enable_pinch_zoom(pw)
    except Exception:
        pass
    return pw, curve


def apply_viewbox_limits(pw: pg.PlotWidget, fs: float):
    """Clamp plot navigation/autorange.

    - X within [10 Hz, fs/2]
    - Prevent zooming out beyond full X span
    - Y within [-96, 24] and at least 2 dB tall
    """
    try:
        vb = pw.getViewBox()
        import math
        # Plot uses log-x; ViewBox limits are in view coordinates (log10 space).
        x0 = 10.0
        x1 = max(10.0, float(fs) / 2.0)
        lx0 = math.log10(x0)
        lx1 = math.log10(x1)
        vb.setLimits(
            xMin=lx0,
            xMax=lx1,
            maxXRange=(lx1 - lx0),
            yMin=-96.0,
            yMax=24.0,
            minYRange=2.0,
        )
        vb.setDefaultPadding(0.02)
    except Exception:
        pass


def add_reset_button(pw: pg.PlotWidget, fs: float):
    """Rename the default auto button and add a Reset button beside it.

    Reset sets the view back to the default constrained range.
    """
    try:
        pi = pw.getPlotItem()
        # Rename the built-in auto button if present
        try:
            btn = getattr(pi, 'autoBtn', None)
            if btn is not None:
                btn.setText('Auto')
                btn.setToolTip('Auto-range to fit data')
        except Exception:
            pass

        # Create a small reset tool button
        reset = QtWidgets.QToolButton()
        reset.setText('Reset')
        reset.setAutoRaise(True)
        reset.setToolTip('Reset view to default range')

        def on_reset():
            try:
                apply_viewbox_limits(pw, fs)
                # Also explicitly reset to full constrained range
                import math
                x0 = math.log10(10.0)
                x1 = math.log10(max(10.0, float(fs)/2.0))
                vb = pw.getViewBox()
                vb.enableAutoRange(x=False, y=False)
                vb.setXRange(x0, x1, padding=0.0)
                vb.setYRange(-24.0, 24.0, padding=0.05)
            except Exception:
                pass

        reset.clicked.connect(on_reset)

        proxy = QtWidgets.QGraphicsProxyWidget()
        proxy.setWidget(reset)
        # Try to place next to the auto button in the buttons layout
        placed = False
        try:
            bl = getattr(pi, 'buttons', None)
            if bl is not None and hasattr(bl, 'layout'):
                lay = bl.layout
                # add to the next column in first row
                lay.addItem(proxy, 0, lay.columnCount())
                placed = True
        except Exception:
            placed = False
        if not placed:
            # Fallback: add to plot item layout in top-right corner cell
            try:
                pi.layout.addItem(proxy, 0, 3)
            except Exception:
                pass
    except Exception:
        pass


class _PinchFilter(QtCore.QObject):
    def __init__(self, pw: pg.PlotWidget):
        super().__init__(pw)
        self._pw = pw
        self._vb = pw.getViewBox()
        try:
            # Grab pinch gesture when delivered as QGesture
            pw.viewport().grabGesture(QtCore.Qt.PinchGesture)
        except Exception:
            pass

    def eventFilter(self, obj, ev):
        try:
            et = ev.type()
            # QGesture events (e.g., touchscreen pinch)
            if et == QtCore.QEvent.Type.Gesture:
                g = ev.gesture(QtCore.Qt.PinchGesture)
                if g is not None:
                    sf = float(getattr(g, 'scaleFactor', lambda: 1.0)())
                    if sf > 0 and sf != 1.0:
                        center = self._mouse_view_point()
                        self._zoom(sf, center)
                        ev.accept()
                        return True
            # macOS trackpad native pinch (Qt6)
            if hasattr(QtCore, 'QNativeGestureEvent') and et == QtCore.QEvent.Type.NativeGesture:
                # In PySide6, event has gestureType/value
                gtype = getattr(ev, 'gestureType', lambda: None)()
                if gtype == getattr(QtCore.Qt, 'ZoomNativeGesture', None):
                    val = float(getattr(ev, 'value', lambda: 0.0)())
                    sf = 1.0 + val
                    if sf > 0 and sf != 1.0:
                        center = self._mouse_view_point()
                        self._zoom(sf, center)
                        ev.accept()
                        return True
        except Exception:
            pass
        return False

    def _zoom(self, scale_factor: float, center: QtCore.QPointF | None = None):
        """Zoom both axes around center in view coords (x=log10 space, y=linear)."""
        try:
            (x0, x1), (y0, y1) = self._vb.viewRange()
            if center is None:
                cx = 0.5 * (x0 + x1)
                cy = 0.5 * (y0 + y1)
            else:
                cx = float(center.x())
                cy = float(center.y())
            # X zoom (log-x space)
            left = cx - x0
            right = x1 - cx
            # Y zoom (linear)
            bottom = cy - y0
            top = y1 - cy
            sf = max(scale_factor, 1e-6)
            self._vb.setXRange(cx - left / sf, cx + right / sf, padding=0.0)
            self._vb.setYRange(cy - bottom / sf, cy + top / sf, padding=0.0)
        except Exception:
            pass

    def _mouse_view_point(self) -> QtCore.QPointF | None:
        try:
            # map global cursor to scene, then to view (log10 x space)
            global_pos = QtGui.QCursor.pos()
            vp = self._pw.viewport().mapFromGlobal(global_pos)
            scene_pt = self._pw.mapToScene(vp)
            view_pt = self._vb.mapSceneToView(scene_pt)
            return view_pt
        except Exception:
            return None


def _enable_pinch_zoom(pw: pg.PlotWidget):
    try:
        flt = _PinchFilter(pw)
        pw.viewport().installEventFilter(flt)
        # Keep a reference to avoid GC
        if not hasattr(pw, '_pinchFilters'):
            pw._pinchFilters = []
        pw._pinchFilters.append(flt)
    except Exception:
        pass


# Note: we previously experimented with custom log-axis tick thinning and label
# styling to reduce overlap. Those changes have been rolled back for stability
# across pyqtgraph versions. If needed in the future, consider reintroducing a
# custom AxisItem with cautious feature detection.


def q_to_hex_twos(v: float, frac_bits: int) -> str:
    scale = 1 << frac_bits
    x = int(round(v * scale))
    # Saturate to 32-bit signed range
    if x > 0x7FFFFFFF:
        x = 0x7FFFFFFF
    if x < -0x80000000:
        x = -0x80000000
    u = x & 0xFFFFFFFF
    return f"0x{u:08X}"

def q_to_hex_twos_floor(v: float, frac_bits: int) -> str:
    """Two's complement hex using floor quantization (PPC3-like).

    Scales by 2^frac_bits and applies floor() before saturating to int32.
    Useful to match TI PPC3 behavior for A1/A2.
    """
    import math
    scale = 1 << frac_bits
    x = int(math.floor(v * scale))
    if x > 0x7FFFFFFF:
        x = 0x7FFFFFFF
    if x < -0x80000000:
        x = -0x80000000
    u = x & 0xFFFFFFFF
    return f"0x{u:08X}"


def notify(widget: QtWidgets.QWidget, text: str, timeout_ms: int = 4000):
    """Show a transient notification via the parent window's status bar."""
    if widget is None:
        return
    win = widget.window()
    if win is not None and hasattr(win, "notify"):
        win.notify(text, timeout_ms)

def hex_twos_to_float(s: str, frac_bits: int) -> float:
    """Parse a 32-bit two's complement hex string to float with given frac bits.

    Accepts strings like "0x7FFFFFFF" or "7fffffff". Returns the signed value
    divided by 2^frac_bits.
    """
    s = s.strip()
    if s.lower().startswith('0x'):
        s = s[2:]
    if len(s) > 8:
        s = s[-8:]
    u = int(s, 16)
    if u & 0x80000000:
        u = -((~u + 1) & 0xFFFFFFFF)
    return float(u) / float(1 << frac_bits)


class _LogMinorAxis(pg.AxisItem):
    """Bottom log axis with dense grid, sparse labels.

    - Grid/ticks: all decade majors and all 0.1 steps between (via logTickValues).
    - Labels: always at majors; among minors, only at 0.2, 0.4, 0.6, 0.8.
    """
    def logTickStrings(self, values, scale, spacing):  # noqa: N802 (pyqtgraph API)
        """Keep labels for majors and only 0.2/0.4/0.6/0.8 minors.

        All tick lines are still drawn; undesired minor labels are blanked.
        """
        # Use default formatting from AxisItem for consistency
        base = pg.AxisItem.logTickStrings(self, values, scale, spacing)

        targets = (
            math.log10(2.0),
            math.log10(4.0),
            math.log10(6.0),
            math.log10(8.0),
        )
        tol = 1e-3
        out = []
        for v, s in zip(values, base):
            frac = v - math.floor(v)
            is_major = (abs(frac) < tol) or (abs(frac - 1.0) < tol)
            is_target_minor = any(abs(frac - t) < tol for t in targets)
            out.append(s if (is_major or is_target_minor) else "")
        return out
