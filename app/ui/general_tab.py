from __future__ import annotations

from PySide6 import QtWidgets, QtCore, QtGui
from pathlib import Path

from ..device_interface.device_link_manager import get_device_link_manager
from ..device_interface.device_write_manager import get_device_write_manager, JournalWrite
from ..device_interface.record_ids import TYPE_APP_STATE, TYPE_TAS_CONFIG, REC_STATE_BOARD_NAME
from ..device_interface.program_tas3251 import load_simple_regs, build_payload_tas3251
from ..device_interface.program_es9821 import load_es9821_pairs, build_payload_es9821
from ..device_interface.state_sidecar import pack_board_name, sanitize_board_name
from .util import notify


class GeneralTab(QtWidgets.QWidget):
    """General device utilities and multi-device management UI."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, dev_mode: bool = False):
        super().__init__(parent)
        self._link_mgr = get_device_link_manager()
        self._writer = get_device_write_manager()
        self._devices: list[dict[str, str]] = []
        self._dev_mode = bool(dev_mode)
        self._maps_dir = Path(__file__).resolve().parents[2] / "app" / "eqcore" / "maps"

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Row 0: Load From Device controls
        load_ctrl = QtWidgets.QWidget(self)
        load_ctrl_l = QtWidgets.QHBoxLayout(load_ctrl)
        load_ctrl_l.setContentsMargins(0, 0, 0, 0)
        load_ctrl_l.setSpacing(8)
        self.combo_load_source = QtWidgets.QComboBox(self)
        self.combo_load_source.setToolTip("Select source amp")
        self.combo_load_source.currentIndexChanged.connect(self._sync_from_selected)
        load_ctrl_l.addWidget(self.combo_load_source, 1)
        self.btn_load_from_device = QtWidgets.QPushButton("Load From Device")
        self.btn_load_from_device.setToolTip("Read settings from selected device and update the UI")
        self.btn_load_from_device.clicked.connect(self._on_load_from_device)
        load_ctrl_l.addWidget(self.btn_load_from_device, 0)
        grid.addWidget(load_ctrl, 0, 0, 1, 1)

        load_desc = QtWidgets.QLabel(
            "Loads settings from the selected amp "
            "and populates the tabs. Does not program DSP."
        )
        load_desc.setWordWrap(True)
        grid.addWidget(load_desc, 0, 1, 1, 1)

        # Row 1: UID controls
        uid_ctrl = QtWidgets.QWidget(self)
        uid_ctrl_l = QtWidgets.QHBoxLayout(uid_ctrl)
        uid_ctrl_l.setContentsMargins(0, 0, 0, 0)
        uid_ctrl_l.setSpacing(8)
        self.edit_uid = QtWidgets.QLineEdit("")
        self.edit_uid.setReadOnly(True)
        self.edit_uid.setPlaceholderText("MCU UID (96-bit)")
        uid_ctrl_l.addWidget(self.edit_uid, 1)
        self.btn_copy_uid = QtWidgets.QPushButton("Copy")
        self.btn_copy_uid.clicked.connect(self._on_copy_uid)
        uid_ctrl_l.addWidget(self.btn_copy_uid, 0)
        self.btn_read_uid = QtWidgets.QPushButton("Read MCU UID")
        self.btn_read_uid.setToolTip("Read UID from selected device")
        self.btn_read_uid.clicked.connect(self._on_read_uid)
        uid_ctrl_l.addWidget(self.btn_read_uid, 0)
        grid.addWidget(uid_ctrl, 1, 0, 1, 1)

        uid_desc = QtWidgets.QLabel(
            "Reads 96-bit hardware unique ID for the selected amp."  # the STM32 96-bit hardware unique ID
        )
        uid_desc.setWordWrap(True)
        grid.addWidget(uid_desc, 1, 1, 1, 1)

        # Row 2: Board name write
        name_ctrl = QtWidgets.QWidget(self)
        name_ctrl_l = QtWidgets.QHBoxLayout(name_ctrl)
        name_ctrl_l.setContentsMargins(0, 0, 0, 0)
        name_ctrl_l.setSpacing(8)
        self.edit_board_name = QtWidgets.QLineEdit("")
        self.edit_board_name.setMaxLength(25)
        self.edit_board_name.setPlaceholderText("Board Name (ASCII, max 25 chars)")
        rx = QtCore.QRegularExpression(r"[ -~]{0,25}")
        self.edit_board_name.setValidator(QtGui.QRegularExpressionValidator(rx, self))
        name_ctrl_l.addWidget(self.edit_board_name, 1)
        self.btn_save_board_name = QtWidgets.QPushButton("Save Name To Device")
        self.btn_save_board_name.setToolTip("Save the board name to the selected amp")
        self.btn_save_board_name.clicked.connect(self._on_save_board_name)
        name_ctrl_l.addWidget(self.btn_save_board_name, 0)
        grid.addWidget(name_ctrl, 2, 0, 1, 1)

        name_desc = QtWidgets.QLabel(
            "Stores a user-defined board name on the selected amp. "
            "Name must be printable ASCII and up to 25 characters."
        )
        name_desc.setWordWrap(True)
        grid.addWidget(name_desc, 2, 1, 1, 1)

        self.btn_erase = None
        self.btn_factory_reset = QtWidgets.QPushButton("Factory Reset")
        self.btn_factory_reset.setToolTip("Erase saved settings on the selected amp and restore the default TAS3251 and ES9821 settings.")
        self.btn_factory_reset.clicked.connect(self._on_factory_reset)
        grid.addWidget(self.btn_factory_reset, 3, 0, 1, 1)

        factory_desc = QtWidgets.QLabel(
            "Recovery utility: erases the selected amp's saved settings, then writes the default "
            "TAS3251 and ES9821 baseline settings."
        )
        factory_desc.setWordWrap(True)
        grid.addWidget(factory_desc, 3, 1, 1, 1)

        self.btn_program_tas = None
        self.btn_program_es = None
        if self._dev_mode:
            # Row 4: Erase EEPROM (Journal)
            self.btn_erase = QtWidgets.QPushButton("Erase EEPROM (Journal)")
            self.btn_erase.setToolTip("Fills the selected amp's 24C256 with 0xFF via !fill")
            self.btn_erase.clicked.connect(self._on_erase)
            grid.addWidget(self.btn_erase, 4, 0, 1, 1)

            erase_desc = QtWidgets.QLabel(
                "Dangerous: erases the selected amp's entire on-board journal (all saved profiles/records)."
            )
            erase_desc.setWordWrap(True)
            grid.addWidget(erase_desc, 4, 1, 1, 1)

            self.btn_program_tas = QtWidgets.QPushButton("Program TAS3251 Maps")
            self.btn_program_tas.setToolTip("Write TAS3251 program memory and register tuning maps to the selected amp.")
            self.btn_program_tas.clicked.connect(self._on_program_tas)
            grid.addWidget(self.btn_program_tas, 5, 0, 1, 1)

            tas_desc = QtWidgets.QLabel(
                "Developer utility: writes shabrang_tas_program_memory.jsonl and "
                "shabrang_tas_register_tuning.jsonl to the selected amp."
            )
            tas_desc.setWordWrap(True)
            grid.addWidget(tas_desc, 5, 1, 1, 1)

            self.btn_program_es = QtWidgets.QPushButton("Program ES9821 Minimal Map")
            self.btn_program_es.setToolTip("Write shabrang_es9821_minimal.jsonl to the selected amp at I2C address 0x20.")
            self.btn_program_es.clicked.connect(self._on_program_es9821_minimal)
            grid.addWidget(self.btn_program_es, 6, 0, 1, 1)

            es_desc = QtWidgets.QLabel(
                "Developer utility: writes shabrang_es9821_minimal.jsonl to the selected amp "
                "using ES9821 journal record 0x21/0x00 and I2C address 0x20."
            )
            es_desc.setWordWrap(True)
            grid.addWidget(es_desc, 6, 1, 1, 1)

        root.addLayout(grid)

        # Live list of connected amps.
        gb = QtWidgets.QGroupBox("Connected Amps")
        gbl = QtWidgets.QVBoxLayout(gb)
        self.tbl_devices = QtWidgets.QTableWidget(0, 4, self)
        self.tbl_devices.setHorizontalHeaderLabels(["Name", "UID", "Port", "Status"])
        self.tbl_devices.verticalHeader().setVisible(False)
        self.tbl_devices.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tbl_devices.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tbl_devices.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.tbl_devices.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.tbl_devices.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.tbl_devices.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        gbl.addWidget(self.tbl_devices)
        root.addWidget(gb, 1)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color: palette(mid)")
        root.addWidget(self.lbl_status)

        self.set_devices([])

    # ---------- public API ----------

    def set_devices(self, devices: list[dict[str, str]]):
        self._devices = [dict(d) for d in (devices or [])]
        prev_uid = self.selected_uid()

        self.combo_load_source.blockSignals(True)
        self.combo_load_source.clear()
        for d in self._devices:
            if str(d.get("status", "responsive")).lower() != "responsive":
                continue
            label = d.get("display") or d.get("uid") or d.get("port", "")
            uid = d.get("uid", "")
            self.combo_load_source.addItem(label, uid)
        self.combo_load_source.blockSignals(False)

        # Restore previous selection when possible.
        idx = -1
        if prev_uid:
            for i in range(self.combo_load_source.count()):
                if str(self.combo_load_source.itemData(i) or "").upper() == prev_uid.upper():
                    idx = i
                    break
        if idx < 0 and self.combo_load_source.count() > 0:
            idx = 0
        if idx >= 0:
            self.combo_load_source.setCurrentIndex(idx)

        self._rebuild_device_table()
        self._sync_from_selected()

    def selected_uid(self) -> str:
        return str(self.combo_load_source.currentData() or "").strip().upper()

    def get_board_name(self) -> str:
        return sanitize_board_name(self.edit_board_name.text(), max_len=25)

    def set_board_name(self, name: str):
        self.edit_board_name.setText(sanitize_board_name(name, max_len=25))

    # ---------- internal ----------

    def _find_selected_device(self) -> dict[str, str] | None:
        uid = self.selected_uid()
        if not uid:
            return None
        for d in self._devices:
            if str(d.get("uid", "")).upper() == uid:
                return d
        return None

    def _sync_from_selected(self):
        d = self._find_selected_device()
        has_dev = d is not None
        self.btn_load_from_device.setEnabled(has_dev)
        self.btn_read_uid.setEnabled(has_dev)
        self.btn_save_board_name.setEnabled(has_dev)
        self.btn_factory_reset.setEnabled(has_dev)
        if self.btn_erase is not None:
            self.btn_erase.setEnabled(has_dev)
        if self.btn_program_tas is not None:
            self.btn_program_tas.setEnabled(has_dev)
        if self.btn_program_es is not None:
            self.btn_program_es.setEnabled(has_dev)
        self.btn_copy_uid.setEnabled(bool(self.edit_uid.text().strip()))

        if not d:
            self.edit_uid.setText("")
            self.edit_board_name.setText("")
            return

        uid = str(d.get("uid", ""))
        name = str(d.get("name", ""))
        self.edit_uid.setText(uid)
        if not self.edit_board_name.hasFocus():
            self.edit_board_name.setText(sanitize_board_name(name, max_len=25))
        self.btn_copy_uid.setEnabled(bool(uid))

    def _rebuild_device_table(self):
        self.tbl_devices.setRowCount(len(self._devices))
        for r, d in enumerate(self._devices):
            status = str(d.get("status", "responsive")).lower()
            name = str(d.get("display", ""))
            uid = str(d.get("uid", ""))
            port = str(d.get("port", ""))
            if not name and status != "responsive":
                name = "Non-responsive"
            status_txt = "Responsive" if status == "responsive" else "Non-responsive"
            self.tbl_devices.setItem(r, 0, QtWidgets.QTableWidgetItem(name))
            self.tbl_devices.setItem(r, 1, QtWidgets.QTableWidgetItem(uid if uid else "-"))
            self.tbl_devices.setItem(r, 2, QtWidgets.QTableWidgetItem(port))
            self.tbl_devices.setItem(r, 3, QtWidgets.QTableWidgetItem(status_txt))

    def _on_erase(self):
        if not self._confirm_erase():
            return
        uid = self.selected_uid()
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Erase EEPROM", "No target amp selected")
            return
        paused = self._pause_background_activity()
        self.btn_erase.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText("Erasing EEPROM... this can take a few seconds...")
        QtWidgets.QApplication.processEvents()

        try:
            ok = self._erase_uid(uid)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Erase EEPROM", f"Failed: {e}")
            self._resume_background_activity(paused)
            self._restore_after(old_cursor)
            return

        if ok:
            self.lbl_status.setText("EEPROM erase completed (OK FILL).")
            QtWidgets.QMessageBox.information(self, "Erase EEPROM", "Completed: EEPROM erased")
        else:
            self.lbl_status.setText("EEPROM erase failed or timed out.")
            QtWidgets.QMessageBox.warning(self, "Erase EEPROM", "Failed: no OK FILL received")
        self._resume_background_activity(paused)
        self._restore_after(old_cursor)

    def _confirm_erase(self) -> bool:
        m = QtWidgets.QMessageBox(self)
        m.setIcon(QtWidgets.QMessageBox.Warning)
        m.setWindowTitle("Erase EEPROM")
        m.setText("Erase the selected amp's EEPROM journal?")
        m.setInformativeText("This removes all saved records (EQ, config, etc.). Use only for recovery.")
        m.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        m.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        return m.exec() == QtWidgets.QMessageBox.Ok

    def _confirm_factory_reset(self) -> bool:
        m = QtWidgets.QMessageBox(self)
        m.setIcon(QtWidgets.QMessageBox.Warning)
        m.setWindowTitle("Factory Reset")
        m.setText("Factory reset the selected amp?")
        m.setInformativeText(
            "This erases the amp's saved settings, then rewrites the default TAS3251 and ES9821 settings."
        )
        m.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Ok)
        m.setDefaultButton(QtWidgets.QMessageBox.Cancel)
        return m.exec() == QtWidgets.QMessageBox.Ok

    def _erase_uid(self, uid: str) -> bool:
        def _erase(link) -> bool:
            try:
                link._write_line("!ei")
            except Exception as e:
                raise RuntimeError(f"while starting the erase process: {e}") from e
            try:
                link._write_line("!fill 0 32768 255")
            except Exception as e:
                raise RuntimeError(f"while sending the erase command: {e}") from e
            try:
                return self._wait_for_fill_result(link, timeout_s=30.0)
            except Exception as e:
                raise RuntimeError(f"while waiting for the erase to finish: {e}") from e

        return bool(self._link_mgr.run(_erase, uid=uid, auto=False, retry=False))

    def _wait_for_fill_result(self, link, timeout_s: float = 30.0) -> bool:
        import time

        dl = 0.2
        t0 = time.time()
        while (time.time() - t0) < timeout_s:
            try:
                lines = link.read_lines(dl)
            except Exception as e:
                raise RuntimeError(f"while checking erase progress: {e}") from e
            for ln in lines:
                s = (ln or "").strip().upper()
                if s.startswith("OK FILL"):
                    return True
                if s.startswith("ERR FILL"):
                    return False
            QtWidgets.QApplication.processEvents()
        return False

    def _restore_after(self, old_cursor):
        try:
            self.setCursor(old_cursor)
        except Exception:
            pass
        if self.btn_erase is not None:
            self.btn_erase.setEnabled(True)

    def _pause_background_activity(self) -> dict[str, bool]:
        state: dict[str, bool] = {}
        mw = self.window()
        if mw is None:
            return state
        for name in ("_dev_timer", "_meter_timer", "_meter_anim_timer"):
            timer = getattr(mw, name, None)
            if timer is None:
                continue
            try:
                state[name] = bool(timer.isActive())
                if state[name]:
                    timer.stop()
            except Exception:
                pass
        return state

    def _resume_background_activity(self, state: dict[str, bool]):
        if not state:
            return
        mw = self.window()
        if mw is None:
            return
        for name, was_active in state.items():
            if not was_active:
                continue
            timer = getattr(mw, name, None)
            if timer is None:
                continue
            try:
                timer.start()
            except Exception:
                pass

    def _on_load_from_device(self):
        uid = self.selected_uid()
        if not uid:
            QtWidgets.QMessageBox.information(self, "Load From Device", "No source amp selected")
            return
        try:
            mw = self.window()
            if mw and hasattr(mw, "_on_load_from_device"):
                mw._on_load_from_device(uid=uid)  # type: ignore[attr-defined]
            else:
                QtWidgets.QMessageBox.information(self, "Load From Device", "Not available in this context.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load From Device", str(e))

    def _on_read_uid(self):
        uid = self.selected_uid()
        if not uid:
            self.lbl_status.setText("UID read failed: no device selected.")
            notify(self, "UID read failed: no device selected.")
            return

        self.btn_read_uid.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText("Reading MCU UID...")
        QtWidgets.QApplication.processEvents()

        try:
            uid_hex = self._link_mgr.run(lambda link: link.uid(), uid=uid, auto=False)
        except Exception as e:
            self.lbl_status.setText(f"UID read failed: {e}")
            notify(self, f"UID read failed: {e}")
            self._restore_after_uid(old_cursor)
            return

        if uid_hex:
            self.edit_uid.setText(uid_hex)
            self.lbl_status.setText(f"MCU UID: {uid_hex}")
            notify(self, "MCU UID read successfully.")
        else:
            self.lbl_status.setText("UID read failed: no response.")
            notify(self, "UID read failed: no response.")
        self._restore_after_uid(old_cursor)

    def _on_copy_uid(self):
        txt = self.edit_uid.text().strip()
        if not txt:
            notify(self, "No UID to copy.", 2500)
            return
        cb = QtWidgets.QApplication.clipboard()
        if cb is not None:
            cb.setText(txt)
            notify(self, "MCU UID copied to clipboard.", 2500)

    def _restore_after_uid(self, old_cursor):
        try:
            self.setCursor(old_cursor)
        except Exception:
            pass
        self.btn_read_uid.setEnabled(True)

    def _run_dev_writes(self, title: str, busy_text: str, writes: list[JournalWrite], button: QtWidgets.QPushButton | None):
        uid = self.selected_uid()
        if not uid:
            QtWidgets.QMessageBox.warning(self, title, "No target amp selected")
            return
        if not writes:
            QtWidgets.QMessageBox.warning(self, title, "Nothing to send")
            return

        if button is not None:
            button.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText(busy_text)
        QtWidgets.QApplication.processEvents()

        try:
            res = self._writer.apply(writes, uid=uid, auto=False, retry=True)
        except Exception as e:
            self.lbl_status.setText(f"{title} failed: {e}")
            notify(self, f"{title} failed: {e}")
            self._restore_dev_action(old_cursor, button)
            return

        if res.ok:
            self.lbl_status.setText(f"{title} completed.")
            notify(self, f"{title} completed.")
        else:
            self.lbl_status.setText(f"{title} failed.")
            details = "\n".join(res.failed)
            QtWidgets.QMessageBox.warning(self, title, f"Completed with write errors:\n{details}")
            notify(self, f"{title} failed.")
        self._restore_dev_action(old_cursor, button)

    def _restore_dev_action(self, old_cursor, button: QtWidgets.QPushButton | None):
        try:
            self.setCursor(old_cursor)
        except Exception:
            pass
        if button is not None:
            button.setEnabled(True)

    def _build_tas_writes(self) -> list[JournalWrite]:
        program_path = self._maps_dir / "shabrang_tas_program_memory.jsonl"
        tuning_path = self._maps_dir / "shabrang_tas_register_tuning.jsonl"
        if not program_path.exists() or not tuning_path.exists():
            raise FileNotFoundError("Required TAS3251 map files were not found.")
        program_payload = build_payload_tas3251(load_simple_regs(program_path), 0x4A)
        tuning_payload = build_payload_tas3251(load_simple_regs(tuning_path), 0x4A)
        return [
            JournalWrite(TYPE_TAS_CONFIG, 0x01, program_payload, "TAS PROGRAM"),
            JournalWrite(TYPE_TAS_CONFIG, 0x02, tuning_payload, "TAS TUNING"),
        ]

    def _build_es9821_minimal_writes(self) -> list[JournalWrite]:
        map_path = self._maps_dir / "shabrang_es9821_minimal.jsonl"
        if not map_path.exists():
            raise FileNotFoundError("Required ES9821 map file was not found.")
        payload = build_payload_es9821(load_es9821_pairs(map_path), i2c_addr_7bit=0x20)
        return [JournalWrite(0x21, 0x00, payload, "ES9821 MINIMAL")]

    def _on_program_tas(self):
        try:
            writes = self._build_tas_writes()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Program TAS3251", f"Failed to build TAS3251 payloads: {e}")
            return
        self._run_dev_writes(
            "Program TAS3251",
            "Programming TAS3251 maps...",
            writes,
            self.btn_program_tas,
        )

    def _on_program_es9821_minimal(self):
        try:
            writes = self._build_es9821_minimal_writes()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Program ES9821", f"Failed to build ES9821 payload: {e}")
            return
        self._run_dev_writes(
            "Program ES9821",
            "Programming ES9821 minimal map...",
            writes,
            self.btn_program_es,
        )

    def _on_factory_reset(self):
        uid = self.selected_uid()
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Factory Reset", "No target amp selected")
            return
        if not self._confirm_factory_reset():
            return

        paused = self._pause_background_activity()
        self.btn_factory_reset.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText("Factory reset: erasing EEPROM...")
        QtWidgets.QApplication.processEvents()

        try:
            ok = self._erase_uid(uid)
        except Exception as e:
            self.lbl_status.setText(f"Factory reset failed: {e}")
            notify(self, f"Factory reset failed: {e}")
            self._resume_background_activity(paused)
            self._restore_dev_action(old_cursor, self.btn_factory_reset)
            return
        if not ok:
            self.lbl_status.setText("Factory reset failed during EEPROM erase.")
            QtWidgets.QMessageBox.warning(self, "Factory Reset", "Failed: the device did not confirm completion.")
            notify(self, "Factory reset failed during EEPROM erase.")
            self._resume_background_activity(paused)
            self._restore_dev_action(old_cursor, self.btn_factory_reset)
            return

        self.lbl_status.setText("Factory reset: programming default maps...")
        QtWidgets.QApplication.processEvents()
        try:
            writes = self._build_tas_writes() + self._build_es9821_minimal_writes()
            res = self._writer.apply(writes, uid=uid, auto=False, retry=True)
        except Exception as e:
            self.lbl_status.setText(f"Factory reset failed: {e}")
            QtWidgets.QMessageBox.warning(self, "Factory Reset", f"Programming failed after erase:\n{e}")
            notify(self, f"Factory reset failed: {e}")
            self._resume_background_activity(paused)
            self._restore_dev_action(old_cursor, self.btn_factory_reset)
            return

        if res.ok:
            self.lbl_status.setText("Factory reset completed.")
            notify(self, "Factory reset completed.")
        else:
            self.lbl_status.setText("Factory reset completed with write errors.")
            QtWidgets.QMessageBox.warning(
                self,
                "Factory Reset",
                "Completed with write errors:\n" + "\n".join(res.failed),
            )
            notify(self, "Factory reset completed with write errors.")
        self._resume_background_activity(paused)
        self._restore_dev_action(old_cursor, self.btn_factory_reset)

    def _on_save_board_name(self):
        uid = self.selected_uid()
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Board Name", "No target amp selected")
            return

        raw = self.edit_board_name.text()
        if len(raw) > 25:
            QtWidgets.QMessageBox.warning(self, "Board Name", "Name must be 25 characters or fewer.")
            return
        if any((ord(ch) < 0x20 or ord(ch) > 0x7E) for ch in raw):
            QtWidgets.QMessageBox.warning(self, "Board Name", "Name must use printable ASCII characters only.")
            return
        payload = pack_board_name(raw, max_len=25)

        self.btn_save_board_name.setEnabled(False)
        old_cursor = self.cursor()
        try:
            self.setCursor(QtCore.Qt.BusyCursor)
        except Exception:
            pass
        self.lbl_status.setText("Saving board name to device...")
        QtWidgets.QApplication.processEvents()

        try:
            res = self._writer.apply(
                [JournalWrite(TYPE_APP_STATE, REC_STATE_BOARD_NAME, payload, "STATE BOARD NAME")],
                uid=uid,
                auto=False,
                retry=True,
            )
        except Exception as e:
            self.lbl_status.setText(f"Board name save failed: {e}")
            notify(self, f"Board name save failed: {e}")
            self._restore_after_board_name(old_cursor)
            return

        if res.ok:
            clean_name = sanitize_board_name(raw, max_len=25)
            self._link_mgr.update_cached_name(uid, clean_name)
            self.set_board_name(clean_name)
            self.lbl_status.setText("Board name saved to device.")
            notify(self, "Board name saved to device.")
            # Trigger a refresh to update duplicate-name disambiguation/display labels.
            mw = self.window()
            if mw and hasattr(mw, "_refresh_devices_now"):
                try:
                    mw._refresh_devices_now()  # type: ignore[attr-defined]
                except Exception:
                    pass
        else:
            self.lbl_status.setText("Board name save failed.")
            notify(self, "Board name save failed.")
        self._restore_after_board_name(old_cursor)

    def _restore_after_board_name(self, old_cursor):
        try:
            self.setCursor(old_cursor)
        except Exception:
            pass
        self.btn_save_board_name.setEnabled(True)
