from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class DeviceTargetSelector(QtWidgets.QWidget):
    """Checkbox target selector for multi-device send actions.

    Shows nothing when device count <= 1.
    """

    selectionChanged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._checks: dict[str, QtWidgets.QCheckBox] = {}
        self._uids_order: list[str] = []

        self._root = QtWidgets.QHBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(6)

        self._label = QtWidgets.QLabel("Targets:")
        self._root.addWidget(self._label)

        self._box = QtWidgets.QWidget(self)
        self._box_l = QtWidgets.QHBoxLayout(self._box)
        self._box_l.setContentsMargins(0, 0, 0, 0)
        self._box_l.setSpacing(8)
        self._root.addWidget(self._box)
        self._root.addStretch(1)

        self.setVisible(False)

    def set_devices(self, devices: list[dict[str, str]]):
        # Preserve existing checked state by uid.
        old_states = {uid: cb.isChecked() for uid, cb in self._checks.items()}

        while self._box_l.count():
            item = self._box_l.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._checks.clear()
        self._uids_order = []

        responsive_count = sum(1 for d in devices if str(d.get("status", "responsive")).lower() == "responsive" and str(d.get("uid", "")).strip())
        if responsive_count <= 1:
            self.setVisible(False)
            self.selectionChanged.emit()
            return

        self.setVisible(True)
        for d in devices:
            if str(d.get("status", "responsive")).lower() != "responsive":
                continue
            uid = (d.get("uid") or "").strip().upper()
            if not uid:
                continue
            title = d.get("display") or uid[-5:]
            cb = QtWidgets.QCheckBox(title)
            cb.setChecked(old_states.get(uid, True))
            cb.toggled.connect(self.selectionChanged)
            self._box_l.addWidget(cb)
            self._checks[uid] = cb
            self._uids_order.append(uid)
        self.selectionChanged.emit()

    def selected_uids(self) -> list[str]:
        out: list[str] = []
        for uid in self._uids_order:
            cb = self._checks.get(uid)
            if cb is not None and cb.isChecked():
                out.append(uid)
        return out

    def has_selection(self) -> bool:
        return any(self._checks.get(uid).isChecked() for uid in self._uids_order if self._checks.get(uid) is not None)
