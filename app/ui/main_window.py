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

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Black Horse Sound Designer")
        self.resize(1100, 700)

        tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(tabs)

        # Add tabs in process-flow order: Input Mixer first, then EQ, then Crossover
        self.mixer_tab = InputMixerTab(self)
        tabs.addTab(self.mixer_tab, "Input Mixer")

        self.eq_tab = EqTab(self)
        tabs.addTab(self.eq_tab, "EQ")

        self.xo_tab = CrossoverTab(self)
        tabs.addTab(self.xo_tab, "Crossover")

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
        act_export = tb.addAction('Export Config')
        act_export.triggered.connect(self._on_export)

    def _on_export(self):
        out = export_pf5_from_ui(self, self.xo_tab)
        if out:
            QtWidgets.QMessageBox.information(self, 'Export', f'Wrote {out}')
