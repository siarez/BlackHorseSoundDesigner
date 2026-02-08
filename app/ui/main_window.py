from __future__ import annotations
import math
import os
import time
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
from ..device_interface.device_link_manager import get_device_link_manager

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, dev_mode: bool = False, show_meter: bool = False):
        super().__init__()
        self._dev_mode = bool(dev_mode)
        self._show_meter = bool(show_meter)
        self._link_mgr = get_device_link_manager()
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

        # 20 Hz meter polling
        self._meter_timer = QtCore.QTimer(self)
        self._meter_timer.setInterval(50)
        self._meter_timer.timeout.connect(self._poll_levels)
        # 30 FPS display decay/update
        self._meter_anim_timer = QtCore.QTimer(self)
        self._meter_anim_timer.setInterval(33)
        self._meter_anim_timer.timeout.connect(self._tick_meter_decay)
        self._meter_enabled = hasattr(self, 'level_meter')
        self._meter_level_1 = 0.0
        self._meter_level_2 = 0.0
        self._meter_raw_1 = 0
        self._meter_raw_2 = 0
        self._meter_decay_db_per_s = 6.0
        self._meter_min_dbfs = -60.0
        self._meter_max_dbfs = 0.0
        self._meter_dbfs_offset = float(os.environ.get("BH_METER_DBFS_OFFSET", "0.0") or 0.0)
        self._meter_calibration_mode = (os.environ.get("BH_METER_CAL_MODE", "0") or "").strip().lower() in {"1", "true", "yes", "on"}
        self._meter_show_raw = (os.environ.get("BH_METER_SHOW_RAW", "0") or "").strip().lower() in {"1", "true", "yes", "on"}
        self._meter_cal_smooth_s = max(0.0, float(os.environ.get("BH_METER_CAL_SMOOTH_S", "0.25") or 0.25))
        self._meter_cal_disp_1 = 0.0
        self._meter_cal_disp_2 = 0.0
        self._meter_cal_last_s = time.monotonic()
        self._meter_last_tick_s = time.monotonic()
        if hasattr(self, 'level_meter'):
            try:
                mode = "CAL" if self._meter_calibration_mode else "PEAK"
                self.level_meter.set_hint(f"starting... [{mode}] (offset {self._meter_dbfs_offset:+.1f} dB)")
                self.level_meter.set_scale_db(self._meter_min_dbfs, self._meter_max_dbfs)
                self.level_meter.set_values_text(self._format_meter_text(float("-inf"), 0), self._format_meter_text(float("-inf"), 0))
            except Exception:
                pass
        if self._meter_enabled:
            self._meter_timer.start()
            if not self._meter_calibration_mode:
                self._meter_anim_timer.start()

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

    def _poll_levels(self):
        if not getattr(self, '_meter_enabled', False):
            return
        if not hasattr(self, 'level_meter'):
            return
        try:
            def _read_levels(link):
                vEE = link.esr(0xEE)
                vED = link.esr(0xED)
                vEF = link.esr(0xEF)
                vF0 = link.esr(0xF0)
                if None in (vEE, vED, vEF, vF0):
                    raise RuntimeError("read error")
                # ES9821 peak readback words: CH1 = EE:ED, CH2 = F0:EF (MSB:LSB).
                ch1 = ((int(vEE) & 0xFF) << 8) | (int(vED) & 0xFF)
                ch2 = ((int(vF0) & 0xFF) << 8) | (int(vEF) & 0xFF)
                return ch1, ch2

            result = self._link_mgr.run_if_idle(_read_levels, auto=True, retry=False)
            if result is None:
                return
            ch1, ch2 = result
            self._meter_raw_1 = int(ch1)
            self._meter_raw_2 = int(ch2)
            p1 = max(0.0, min(1.0, int(ch1) / 65535.0))
            p2 = max(0.0, min(1.0, int(ch2) / 65535.0))
            if self._meter_calibration_mode:
                # Direct mode for calibration: no app-side hold/decay.
                if self._meter_cal_smooth_s > 0.0:
                    now = time.monotonic()
                    dt = max(0.001, min(0.5, now - self._meter_cal_last_s))
                    self._meter_cal_last_s = now
                    alpha = math.exp(-dt / self._meter_cal_smooth_s)
                    self._meter_cal_disp_1 = (alpha * self._meter_cal_disp_1) + ((1.0 - alpha) * p1)
                    self._meter_cal_disp_2 = (alpha * self._meter_cal_disp_2) + ((1.0 - alpha) * p2)
                else:
                    self._meter_cal_disp_1 = p1
                    self._meter_cal_disp_2 = p2
                self._meter_level_1 = self._meter_cal_disp_1
                self._meter_level_2 = self._meter_cal_disp_2
                dbfs_1 = self._amp_to_dbfs(self._meter_cal_disp_1) + self._meter_dbfs_offset
                dbfs_2 = self._amp_to_dbfs(self._meter_cal_disp_2) + self._meter_dbfs_offset
                self.level_meter.set_levels_db(dbfs_1, dbfs_2)
                self.level_meter.set_values_text(
                    self._format_meter_text(dbfs_1, self._meter_raw_1),
                    self._format_meter_text(dbfs_2, self._meter_raw_2),
                )
            else:
                self._meter_level_1 = max(self._meter_level_1, p1)
                self._meter_level_2 = max(self._meter_level_2, p2)
            port = self._link_mgr.current_port() or ""
            mode = "CAL" if self._meter_calibration_mode else "PEAK"
            self.level_meter.set_hint(f"{port} [{mode}] ({self._meter_dbfs_offset:+.1f} dB)")
        except Exception:
            self.level_meter.set_hint('No data')

    def _tick_meter_decay(self):
        if not getattr(self, '_meter_enabled', False):
            return
        if not hasattr(self, 'level_meter'):
            return
        if self._meter_calibration_mode:
            return
        now = time.monotonic()
        dt = max(0.0, min(0.25, now - self._meter_last_tick_s))
        self._meter_last_tick_s = now
        # Exponential decay in dB/second.
        decay = 10.0 ** (-(self._meter_decay_db_per_s * dt) / 20.0)
        self._meter_level_1 *= decay
        self._meter_level_2 *= decay
        dbfs_1 = self._amp_to_dbfs(self._meter_level_1) + self._meter_dbfs_offset
        dbfs_2 = self._amp_to_dbfs(self._meter_level_2) + self._meter_dbfs_offset
        self.level_meter.set_levels_db(dbfs_1, dbfs_2)
        self.level_meter.set_values_text(
            self._format_meter_text(dbfs_1, self._meter_raw_1),
            self._format_meter_text(dbfs_2, self._meter_raw_2),
        )

    def _amp_to_dbfs(self, amp_norm: float) -> float:
        return 20.0 * math.log10(max(0.0, float(amp_norm), 1e-9))

    def _format_meter_text(self, dbfs: float, raw_code: int) -> str:
        if dbfs <= -180.0:
            base = "-inf dBFS"
        else:
            base = f"{dbfs:.1f} dBFS"
        if not self._meter_show_raw:
            return base
        if dbfs <= -180.0:
            base_short = "-inf"
        else:
            base_short = f"{dbfs:.1f}"
        return f"S:{base_short}\nR:{int(raw_code)}"

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
        from ..device_interface.record_ids import (
            TYPE_APP_STATE, REC_STATE_EQ, REC_STATE_XO, REC_STATE_MIXER, REC_STATE_MIXGAIN, REC_STATE_XBAR,
        )
        from ..device_interface.state_sidecar import (
            unpack_eq_state, unpack_xo_state, unpack_q97_values,
        )
        applied = []
        try:
            def _read_all(link):
                return {
                    'eq': link.jrdb(TYPE_APP_STATE, REC_STATE_EQ),
                    'xo': link.jrdb(TYPE_APP_STATE, REC_STATE_XO),
                    'mixer': link.jrdb(TYPE_APP_STATE, REC_STATE_MIXER),
                    'mix_gain': link.jrdb(TYPE_APP_STATE, REC_STATE_MIXGAIN),
                    'xbar': link.jrdb(TYPE_APP_STATE, REC_STATE_XBAR),
                }

            blobs = self._link_mgr.run(_read_all, auto=True)

            data = blobs.get('eq')
            if data:
                dec = unpack_eq_state(data)
                if dec.get('fs'):
                    try:
                        self.eq_tab.set_fs(float(dec['fs']))
                    except Exception:
                        pass
                self.eq_tab.apply_state_dict(dec.get('eq') or [])
                applied.append('EQ')

            data = blobs.get('xo')
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

            data = blobs.get('mixer')
            if data:
                order = ['LefttoLeft', 'RighttoLeft', 'LefttoRight', 'RighttoRight']
                vals = unpack_q97_values(data, order)
                if vals:
                    self.mixer_tab.apply_state_dict(vals)
                    applied.append('Input Mixer')

            data = blobs.get('mix_gain')
            if data:
                order = list(self.mix_gain_tab.NAMES.keys()) if hasattr(self.mix_gain_tab, 'NAMES') else []
                vals = unpack_q97_values(data, order)
                if vals:
                    self.mix_gain_tab.apply_state_dict(vals)
                    applied.append('Mix/Gain Adjust')

            data = blobs.get('xbar')
            if data:
                order = list(self.xbar_tab.NAMES) if hasattr(self.xbar_tab, 'NAMES') else []
                vals = unpack_q97_values(data, order)
                if vals:
                    self.xbar_tab.apply_state_dict(vals)
                    applied.append('Output Cross Bar')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Load From Device', f'Failed to read device: {e}')
            return
        if applied:
            QtWidgets.QMessageBox.information(self, 'Load From Device', 'Loaded: ' + ', '.join(applied))
        else:
            QtWidgets.QMessageBox.information(self, 'Load From Device', 'No sidecar (0x53) records found')
