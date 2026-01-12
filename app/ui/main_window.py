from __future__ import annotations
from PySide6 import QtWidgets

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

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, dev_mode: bool = False):
        super().__init__()
        self._dev_mode = bool(dev_mode)
        self.setWindowTitle("Black Horse Sound Designer")
        self.resize(1100, 700)

        # Menu bar: File -> Save/Load State, Load From Device (Phase 2)
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

        tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(tabs)

        # General utilities (recovery, erase, etc.)
        self.general_tab = GeneralTab(self)
        tabs.addTab(self.general_tab, "General")

        # Add tabs in process-flow order: Input Mixer first, then EQ, then Crossover
        self.mixer_tab = InputMixerTab(self)
        tabs.addTab(self.mixer_tab, "Input Mixer")

        self.eq_tab = EqTab(self)
        tabs.addTab(self.eq_tab, "EQ")

        self.xo_tab = CrossoverTab(self)
        tabs.addTab(self.xo_tab, "Crossover")

        self.mix_gain_tab = MixGainAdjustTab(self)
        tabs.addTab(self.mix_gain_tab, "Mix/Gain Adjust")

        self.xbar_tab = OutputCrossbarTab(self)
        tabs.addTab(self.xbar_tab, "Output Cross Bar")

        if self._dev_mode:
            self.coef_tab = CoefCheckTab(self)
            tabs.addTab(self.coef_tab, "Coef Check")

            self.journal_tab = JournalTab(self)
            tabs.addTab(self.journal_tab, "Device Journal")

            self.i2c_script_tab = I2cScriptTab(self)
            tabs.addTab(self.i2c_script_tab, "I2C Script")

            self.es9821_tab = Es9821Tab(self)
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

    def _on_export(self):
        out = export_pf5_from_ui(self, self.xo_tab)
        if out:
            QtWidgets.QMessageBox.information(self, 'Export', f'Wrote {out}')

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
