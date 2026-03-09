from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Optional, TypeVar

from .cdc_link import CdcLink, auto_detect_port, list_serial_ports

T = TypeVar("T")


@dataclass
class _PortEntry:
    lock: threading.RLock
    link: Optional[CdcLink] = None


class DeviceLinkManager:
    """Multi-device serial link manager.

    Maintains one CdcLink per serial port and serializes access per port.
    Also tracks discovered devices by UID so callers can target a specific amp.
    """

    def __init__(self):
        self._meta_lock = threading.RLock()
        self._entries: dict[str, _PortEntry] = {}
        self._devices: list[dict[str, str]] = []
        self._uid_to_port: dict[str, str] = {}
        self._identity_cache: dict[str, tuple[str, str]] = {}
        self._default_uid: str = ""

    def is_connected(self) -> bool:
        with self._meta_lock:
            return any(e.link is not None for e in self._entries.values())

    def current_port(self) -> str:
        with self._meta_lock:
            if self._default_uid:
                p = self._uid_to_port.get(self._default_uid, "")
                if p:
                    return p
            if self._devices:
                return self._devices[0].get("port", "")
            return ""

    def devices(self) -> list[dict[str, str]]:
        with self._meta_lock:
            return [dict(d) for d in self._devices]

    def port_for_uid(self, uid: str) -> str:
        with self._meta_lock:
            return self._uid_to_port.get(uid, "")

    def connect(self, port: str | None = None, *, uid: str | None = None, auto: bool = True) -> str:
        target = self._resolve_port(port=port, uid=uid, auto=auto)
        if not target:
            raise RuntimeError("No device found (auto-detect failed)")
        # Ensure link exists.
        self._run_on_port(target, lambda _link: None, retry=False)
        return target

    def disconnect(self):
        with self._meta_lock:
            items = list(self._entries.items())
        for _port, ent in items:
            if ent.lock.acquire(blocking=False):
                try:
                    self._close_entry_link_locked(ent)
                finally:
                    ent.lock.release()

    def discover_devices(self) -> list[dict[str, str]]:
        ports = self._candidate_ports()
        found: list[dict[str, str]] = []
        nonresponsive: list[dict[str, str]] = []

        for port in ports:
            # Read UID quickly; board name is fetched lazily/cached to keep discovery light.
            uid_probe = self.run_if_idle(
                lambda link: (link.uid(timeout=0.25) or ""),
                port=port,
                auto=False,
                retry=False,
            )
            if uid_probe is None:
                # Busy with active operation; use cached identity if available.
                with self._meta_lock:
                    ident = self._identity_cache.get(port, ("", ""))
                uid, board_name = ident if isinstance(ident, tuple) else ("", "")
                uid = (uid or "").strip().upper()
                board_name = (board_name or "")
                if uid:
                    found.append({"uid": uid, "name": board_name, "port": port, "status": "responsive"})
                else:
                    nonresponsive.append({
                        "uid": "",
                        "name": "",
                        "display": "Non-responsive",
                        "port": port,
                        "status": "non-responsive",
                    })
                continue

            uid = str(uid_probe or "").strip().upper()
            with self._meta_lock:
                cached_uid, cached_name = self._identity_cache.get(port, ("", ""))
            board_name = ""
            if cached_uid == uid and cached_name:
                board_name = cached_name
            elif uid:
                name_probe = self.run_if_idle(
                    lambda link: (link.board_name(timeout=0.25) or ""),
                    port=port,
                    auto=False,
                    retry=False,
                )
                if isinstance(name_probe, str):
                    board_name = name_probe
                elif cached_uid == uid:
                    board_name = cached_name

            uid = (uid or "").strip().upper()
            board_name = (board_name or "")
            if not uid:
                nonresponsive.append({
                    "uid": "",
                    "name": "",
                    "display": "Non-responsive",
                    "port": port,
                    "status": "non-responsive",
                })
                continue
            with self._meta_lock:
                self._identity_cache[port] = (uid, board_name)
            found.append({"uid": uid, "name": board_name, "port": port, "status": "responsive"})

        # Build display names and UID->port map.
        uid_to_port: dict[str, str] = {}
        base_labels: list[str] = []
        for d in found:
            uid = d["uid"]
            uid_to_port[uid] = d["port"]
            short_uid = uid[-5:] if len(uid) >= 5 else uid
            base_labels.append(d["name"] if d["name"] else short_uid)

        counts: dict[str, int] = {}
        for base in base_labels:
            counts[base] = counts.get(base, 0) + 1

        devices_out: list[dict[str, str]] = []
        for d, base in zip(found, base_labels):
            uid = d["uid"]
            short_uid = uid[-5:] if len(uid) >= 5 else uid
            display = base if counts.get(base, 0) <= 1 else f"{base} ({short_uid})"
            devices_out.append({
                "uid": uid,
                "name": d["name"],
                "display": display,
                "port": d["port"],
                "status": "responsive",
            })

        devices_out.sort(key=lambda x: (x.get("display", ""), x.get("uid", "")))
        devices_out.extend(nonresponsive)

        with self._meta_lock:
            self._devices = devices_out
            self._uid_to_port = uid_to_port
            if self._default_uid not in self._uid_to_port:
                self._default_uid = ""
                for d in self._devices:
                    if (d.get("status") == "responsive") and d.get("uid"):
                        self._default_uid = d["uid"]
                        break

        # Prune links for ports no longer present.
        self._prune_ports(set(ports))

        return self.devices()

    def set_default_uid(self, uid: str | None):
        u = (uid or "").strip().upper()
        with self._meta_lock:
            if u and u in self._uid_to_port:
                self._default_uid = u

    def update_cached_name(self, uid: str, name: str):
        """Update cached board name for a known UID (used after rename writes)."""
        u = (uid or "").strip().upper()
        if not u:
            return
        n = str(name or "")
        with self._meta_lock:
            port = self._uid_to_port.get(u, "")
            if not port:
                for d in self._devices:
                    if str(d.get("uid", "")).upper() == u:
                        port = str(d.get("port", ""))
                        break
            if not port:
                return
            self._identity_cache[port] = (u, n)

    def default_uid(self) -> str:
        with self._meta_lock:
            return self._default_uid

    def run(
        self,
        fn: Callable[[CdcLink], T],
        *,
        port: str | None = None,
        uid: str | None = None,
        auto: bool = True,
        retry: bool = True,
    ) -> T:
        target = self._resolve_port(port=port, uid=uid, auto=auto)
        if not target:
            raise RuntimeError("No device found (auto-detect failed)")
        return self._run_on_port(target, fn, retry=retry)

    def run_if_idle(
        self,
        fn: Callable[[CdcLink], T],
        *,
        port: str | None = None,
        uid: str | None = None,
        auto: bool = True,
        retry: bool = True,
    ) -> T | None:
        target = self._resolve_port(port=port, uid=uid, auto=auto)
        if not target:
            return None
        ent = self._get_or_create_entry(target)
        if not ent.lock.acquire(blocking=False):
            return None
        try:
            link = self._ensure_link_locked(target, ent)
            try:
                return fn(link)
            except Exception:
                self._close_entry_link_locked(ent)
                if not retry:
                    raise
                link = self._ensure_link_locked(target, ent)
                return fn(link)
        finally:
            ent.lock.release()

    # ---------- internals ----------

    def _resolve_port(self, *, port: str | None, uid: str | None, auto: bool) -> str:
        target = (port or "").strip()
        if target:
            return target

        u = (uid or "").strip().upper()
        if u:
            with self._meta_lock:
                p = self._uid_to_port.get(u, "")
            if p:
                return p

        if not auto:
            return ""

        devices = self.discover_devices()
        if u:
            for d in devices:
                if d.get("uid", "") == u:
                    return d.get("port", "")
            return ""

        with self._meta_lock:
            if self._default_uid:
                p = self._uid_to_port.get(self._default_uid, "")
                if p:
                    return p

        if devices:
            return devices[0].get("port", "")

        # Compatibility fallback.
        return auto_detect_port()

    def _candidate_ports(self) -> list[str]:
        ports = list_serial_ports()
        out: list[tuple[int, str]] = []
        for p in ports:
            dev = (p.get("device") or "").strip()
            if not dev:
                continue
            prod = (p.get("product") or "").lower()
            manf = (p.get("manufacturer") or "").lower()
            vid = p.get("vid")
            pid = p.get("pid")

            primary = ("shabrang" in prod) or ("black horse audio" in manf)
            vidpid = (vid == 0x0483 and pid == 0x5740)
            if not (primary or vidpid):
                continue
            score = (4 if primary else 0) + (2 if vidpid else 0)
            out.append((score, dev))

        out.sort(key=lambda x: (-x[0], x[1]))
        seen: set[str] = set()
        ordered: list[str] = []
        for _score, dev in out:
            if dev in seen:
                continue
            seen.add(dev)
            ordered.append(dev)
        return ordered

    def _get_or_create_entry(self, port: str) -> _PortEntry:
        with self._meta_lock:
            ent = self._entries.get(port)
            if ent is None:
                ent = _PortEntry(lock=threading.RLock(), link=None)
                self._entries[port] = ent
            return ent

    def _run_on_port(self, port: str, fn: Callable[[CdcLink], T], *, retry: bool) -> T:
        ent = self._get_or_create_entry(port)
        with ent.lock:
            link = self._ensure_link_locked(port, ent)
            try:
                return fn(link)
            except Exception:
                self._close_entry_link_locked(ent)
                if not retry:
                    raise
                link = self._ensure_link_locked(port, ent)
                return fn(link)

    def _ensure_link_locked(self, port: str, ent: _PortEntry) -> CdcLink:
        if ent.link is None:
            ent.link = CdcLink(port)
        return ent.link

    def _close_entry_link_locked(self, ent: _PortEntry):
        if ent.link is not None:
            try:
                ent.link.close()
            except Exception:
                pass
        ent.link = None

    def _prune_ports(self, active_ports: set[str]):
        with self._meta_lock:
            stale = [p for p in self._entries.keys() if p not in active_ports]
        for port in stale:
            ent = self._get_or_create_entry(port)
            if not ent.lock.acquire(blocking=False):
                continue
            try:
                self._close_entry_link_locked(ent)
                with self._meta_lock:
                    # Safe to drop only if still stale.
                    if port in self._entries and port not in active_ports:
                        del self._entries[port]
            finally:
                ent.lock.release()


_MANAGER = DeviceLinkManager()


def get_device_link_manager() -> DeviceLinkManager:
    return _MANAGER
