from __future__ import annotations
from PySide6 import QtWidgets, QtCore

from .eq_tab import EqTab
from .crossover_tab import CrossoverTab
from .coef_check_tab import CoefCheckTab
from .exporter import export_pf5_from_ui
from .input_mixer_tab import InputMixerTab
from .journal_tab import JournalTab
from .es9821_tab import Es9821Tab
from .i2c_script_tab import I2cScriptTab
from .mix_gain_adjust_tab import MixGainAdjustTab
from .output_crossbar_tab import OutputCrossbarTab
from .general_tab import GeneralTab
from .level_meter import LevelMeterWidget

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, dev_mode: bool = False, show_meter: bool = False):
        super().__init__()
        self._dev_mode = bool(dev_mode)
        self._show_meter = bool(show_meter)
        self.setWindowTitle("Black Horse Sound Designer")
        self.resize(1100, 700)

        # Menu bar + status bar
        mbar = self.menuBar()
        m_file = mbar.addMenu("File")
        act_save = m_file.addAction("Save State…")
        act_save.triggered.connect(self._on_save_state)
        act_load = m_file.addAction("Load State…")
        act_load.triggered.connect(self._on_load_state)
        m_file.addSeparator()
        self.act_load_from_device = m_file.addAction("Load From Device")
        # Hooked in Phase 2; keep disabled for now
        self.act_load_from_device.setEnabled(True)
        self.act_load_from_device.triggered.connect(self._on_load_from_device)

        # Central: either tabs-only, or tabs + right-side meter panel
        if self._show_meter:
            central = QtWidgets.QWidget(self)
            h = QtWidgets.QHBoxLayout(central)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            tabs = QtWidgets.QTabWidget(central)
            h.addWidget(tabs, 1)
            # Right panel with level meters
            self.level_meter = LevelMeterWidget(central)
            self.level_meter.setFixedWidth(120)
            frame = QtWidgets.QFrame(central)
            frame.setFrameShape(QtWidgets.QFrame.VLine)
            frame.setFrameShadow(QtWidgets.QFrame.Sunken)
            right_w = QtWidgets.QWidget(central)
            right_w.setLayout(QtWidgets.QHBoxLayout())
            right_w.layout().setContentsMargins(0, 0, 0, 0)
            right_w.layout().setSpacing(0)
            right_w.layout().addWidget(frame)
            right_w.layout().addWidget(self.level_meter)
            h.addWidget(right_w, 0)
            self.setCentralWidget(central)
        else:
            tabs = QtWidgets.QTabWidget(self)
            self.setCentralWidget(tabs)

        # General utilities (recovery, erase, etc.)
        self.general_tab = GeneralTab(tabs)
        tabs.addTab(self.general_tab, "General")

        # Add tabs in process-flow order: Input Mixer first, then EQ, then Crossover
        self.mixer_tab = InputMixerTab(tabs)
        tabs.addTab(self.mixer_tab, "Input Mixer")

        self.eq_tab = EqTab(tabs)
        tabs.addTab(self.eq_tab, "EQ")

        self.xo_tab = CrossoverTab(tabs)
        tabs.addTab(self.xo_tab, "Crossover")

        self.mix_gain_tab = MixGainAdjustTab(tabs)
        tabs.addTab(self.mix_gain_tab, "Mix/Gain Adjust")

        self.xbar_tab = OutputCrossbarTab(tabs)
        tabs.addTab(self.xbar_tab, "Output Cross Bar")

        if self._dev_mode:
            self.coef_tab = CoefCheckTab(tabs)
            tabs.addTab(self.coef_tab, "Coef Check")

            self.journal_tab = JournalTab(tabs)
            tabs.addTab(self.journal_tab, "Device Journal")

            self.i2c_script_tab = I2cScriptTab(tabs)
            tabs.addTab(self.i2c_script_tab, "I2C Script")

            self.es9821_tab = Es9821Tab(tabs)
            tabs.addTab(self.es9821_tab, "ES9821 Regs")


        # Toolbar with Export action
        tb = self.addToolBar('Main')
        act_save_tb = tb.addAction('Save State')
        act_save_tb.triggered.connect(self._on_save_state)
        act_load_tb = tb.addAction('Load State')
        act_load_tb.triggered.connect(self._on_load_state)
        if self._dev_mode:
            tb.addSeparator()
            act_export = tb.addAction('Export Config')
            act_export.triggered.connect(self._on_export)

        # Status bar for transient notifications
        self._status_bar = self.statusBar()
        if self._status_bar:
            self._status_bar.setSizeGripEnabled(False)

        # 5 Hz meter polling (temporarily disabled)
        self._meter_timer = QtCore.QTimer(self)
        self._meter_timer.setInterval(200)
        self._meter_timer.timeout.connect(self._poll_levels)
        self._meter_link = None
        self._meter_enabled = False
        if hasattr(self, 'level_meter'):
            try:
                self.level_meter.set_hint('meter disabled')
            except Exception:
                pass

    def _on_export(self):
        out = export_pf5_from_ui(self, self.xo_tab)
        if out:
            self.notify(f'Exported PF5 to {out}')

    def notify(self, message: str, timeout_ms: int = 4000):
        bar = getattr(self, '_status_bar', None)
        if bar is not None:
            # Basic heuristic: treat messages containing "error"/"failed"/"warn" as warnings.
            lower = (message or "").lower()
            if any(word in lower for word in ("error", "fail", "warning", "err ", "err.")):
                bar.setStyleSheet("QStatusBar { color: #d32f2f; }")  # red
            else:
                bar.setStyleSheet("QStatusBar { color: #2e7d32; }")  # green
            bar.showMessage(message, timeout_ms)

    # ---------------- Level meter polling ----------------
    def _open_meter_link(self):
        if self._meter_link is not None:
            return True
        try:
            from ..device_interface.cdc_link import CdcLink, auto_detect_port
            port = auto_detect_port()
            if not port:
                self.level_meter.set_hint('No device')
                return False
            self._meter_link = CdcLink(port)
            self._meter_port = port
            self.level_meter.set_hint(f'{port}')
            return True
        except Exception:
            self._meter_link = None
            self.level_meter.set_hint('No device')
            return False

    def _close_meter_link(self):
        if self._meter_link is not None:
            try:
                self._meter_link.close()
            except Exception:
                pass
            self._meter_link = None

    def _poll_levels(self):
        # Temporarily disabled unless explicitly enabled
        if not getattr(self, '_meter_enabled', False):
            return
        # Try to open link if needed
        if not hasattr(self, 'level_meter') or not self._open_meter_link():
            self.level_meter.set_levels(0.0, 0.0)
            return
        link = self._meter_link
        try:
            # Read ES9821 peak meters: 0xEE/0xED (ch1 MSB/LSB), 0xEF/0xF0 (ch2 MSB/LSB)
            vEE = link.esr(0xEE)
            vED = link.esr(0xED)
            vEF = link.esr(0xEF)
            vF0 = link.esr(0xF0)
            if None in (vEE, vED, vEF, vF0):
                raise RuntimeError('read error')
            # According to observed behavior, MSB appears at ED/EF, LSB at EE/F0.
            ch1 = ((int(vED) & 0xFF) << 8) | (int(vEE) & 0xFF)
            ch2 = ((int(vEF) & 0xFF) << 8) | (int(vF0) & 0xFF)
            l1 = max(0.0, min(1.0, ch1 / 65535.0))
            l2 = max(0.0, min(1.0, ch2 / 65535.0))
            self.level_meter.set_levels(l1, l2)
            self.level_meter.set_values_text(str(ch1), str(ch2))
            # Show port so user knows we are connected
            self.level_meter.set_hint(getattr(self, '_meter_port', '') or '')
        except Exception:
            # On error, close and retry next tick; show hint
            self._close_meter_link()
            self.level_meter.set_levels(0.0, 0.0)
            self.level_meter.set_values_text("ERR", "ERR")
            self.level_meter.set_hint('No data')

    # ---------------- Save/Load State (JSON) ----------------
    def _gather_state(self) -> dict:
        """Collect cross-tab state as a versioned JSON-serializable dict."""
        from datetime import datetime
        state = {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec='seconds'),
            "fs": int(getattr(self.eq_tab, "_fs", 48000.0)),
            "eq": self.eq_tab.to_state_dict() if hasattr(self.eq_tab, 'to_state_dict') else [],
            "xo": {},
            "xo_misc": {},
            "input_mixer": {},
            "mix_gain": {},
            "xbar": {},
        }
        if hasattr(self.xo_tab, 'to_state_dict'):
            xo = self.xo_tab.to_state_dict()
            state["xo"] = {"A": xo.get("A", []), "B": xo.get("B", [])}
            state["xo_misc"] = xo.get("misc", {})
        if hasattr(self.mixer_tab, 'to_state_dict'):
            state["input_mixer"] = self.mixer_tab.to_state_dict()
        if hasattr(self.mix_gain_tab, 'to_state_dict'):
            state["mix_gain"] = self.mix_gain_tab.to_state_dict()
        if hasattr(self.xbar_tab, 'to_state_dict'):
            state["xbar"] = self.xbar_tab.to_state_dict()
        return state

    def _apply_state(self, state: dict):
        if not isinstance(state, dict):
            return
        fs = state.get("fs")
        if fs is not None:
            try:
                self.eq_tab.set_fs(float(fs))
                self.xo_tab.set_fs(float(fs))
            except Exception:
                pass
        if hasattr(self.eq_tab, 'apply_state_dict'):
            self.eq_tab.apply_state_dict(state.get("eq") or [])
        if hasattr(self.xo_tab, 'apply_state_dict'):
            self.xo_tab.apply_state_dict({
                "A": state.get("xo", {}).get("A", []),
                "B": state.get("xo", {}).get("B", []),
                "misc": state.get("xo_misc", {}),
            })
        if hasattr(self.mixer_tab, 'apply_state_dict'):
            self.mixer_tab.apply_state_dict(state.get("input_mixer") or {})
        if hasattr(self.mix_gain_tab, 'apply_state_dict'):
            self.mix_gain_tab.apply_state_dict(state.get("mix_gain") or {})
        if hasattr(self.xbar_tab, 'apply_state_dict'):
            self.xbar_tab.apply_state_dict(state.get("xbar") or {})

    def _on_save_state(self):
        import json
        dlg = QtWidgets.QFileDialog(self, 'Save State', '', 'JSON Files (*.json);;All Files (*)')
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setDefaultSuffix('json')
        if dlg.exec() != QtWidgets.QFileDialog.Accepted:
            return
        path = dlg.selectedFiles()[0]
        try:
            state = self._gather_state()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            QtWidgets.QMessageBox.information(self, 'Save State', f'Saved state to {path}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Save State', f'Failed to save: {e}')

    def _on_load_state(self):
        import json
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Load State', '', 'JSON Files (*.json);;All Files (*)')
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # Version check (tolerant)
            if isinstance(state, dict) and int(state.get('version', 1)) >= 1:
                self._apply_state(state)
                QtWidgets.QMessageBox.information(self, 'Load State', 'State loaded into UI (not sent to device)')
            else:
                QtWidgets.QMessageBox.warning(self, 'Load State', 'Unsupported or missing state version')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Load State', f'Failed to load: {e}')

    # Placeholder for Phase 2 (device sidecar read)
    def _on_load_from_device(self):
        from ..device_interface.cdc_link import CdcLink, auto_detect_port
        from ..device_interface.record_ids import (
            TYPE_APP_STATE, REC_STATE_EQ, REC_STATE_XO, REC_STATE_MIXER, REC_STATE_MIXGAIN, REC_STATE_XBAR,
        )
        from ..device_interface.state_sidecar import (
            unpack_eq_state, unpack_xo_state, unpack_q97_values,
        )
        port = auto_detect_port()
        if not port:
            QtWidgets.QMessageBox.warning(self, 'Load From Device', 'No device found (auto-detect failed)')
            return
        try:
            link = CdcLink(port)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Load From Device', f'Failed to open {port}: {e}')
            return
        applied = []
        try:
            # EQ
            try:
                data = link.jrdb(TYPE_APP_STATE, REC_STATE_EQ)
                if data:
                    dec = unpack_eq_state(data)
                    if dec.get('fs'):
                        try:
                            self.eq_tab.set_fs(float(dec['fs']))
                        except Exception:
                            pass
                    self.eq_tab.apply_state_dict(dec.get('eq') or [])
                    applied.append('EQ')
            except Exception:
                pass
            # XO
            try:
                data = link.jrdb(TYPE_APP_STATE, REC_STATE_XO)
                if data:
                    dec = unpack_xo_state(data)
                    if dec.get('fs'):
                        try:
                            self.xo_tab.set_fs(float(dec['fs']))
                        except Exception:
                            pass
                    self.xo_tab.apply_state_dict({
                        'A': dec.get('A', []),
                        'B': dec.get('B', []),
                        'misc': dec.get('misc', {}),
                    })
                    applied.append('XO')
            except Exception:
                pass
            # Mixer
            try:
                data = link.jrdb(TYPE_APP_STATE, REC_STATE_MIXER)
                if data:
                    order = ['LefttoLeft','RighttoLeft','LefttoRight','RighttoRight']
                    vals = unpack_q97_values(data, order)
                    if vals:
                        self.mixer_tab.apply_state_dict(vals)
                        applied.append('Input Mixer')
            except Exception:
                pass
            # Mix/Gain Adjust
            try:
                data = link.jrdb(TYPE_APP_STATE, REC_STATE_MIXGAIN)
                if data:
                    order = list(self.mix_gain_tab.NAMES.keys()) if hasattr(self.mix_gain_tab, 'NAMES') else []
                    vals = unpack_q97_values(data, order)
                    if vals:
                        self.mix_gain_tab.apply_state_dict(vals)
                        applied.append('Mix/Gain Adjust')
            except Exception:
                pass
            # Output Cross Bar
            try:
                data = link.jrdb(TYPE_APP_STATE, REC_STATE_XBAR)
                if data:
                    order = list(self.xbar_tab.NAMES) if hasattr(self.xbar_tab, 'NAMES') else []
                    vals = unpack_q97_values(data, order)
                    if vals:
                        self.xbar_tab.apply_state_dict(vals)
                        applied.append('Output Cross Bar')
            except Exception:
                pass
        finally:
            try:
                link.close()
            except Exception:
                pass
        if applied:
            QtWidgets.QMessageBox.information(self, 'Load From Device', 'Loaded: ' + ', '.join(applied))
        else:
            QtWidgets.QMessageBox.information(self, 'Load From Device', 'No sidecar (0x53) records found')
