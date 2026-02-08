from __future__ import annotations

import threading
from typing import Callable, Optional, TypeVar

from .cdc_link import CdcLink, auto_detect_port

T = TypeVar("T")


class DeviceLinkManager:
    """Single-owner serial link manager for the app.

    Keeps one CdcLink open and serializes access through a lock so
    concurrent features (meter polling + tab actions) do not contend
    for the serial port.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._link: Optional[CdcLink] = None
        self._port: str = ""

    def is_connected(self) -> bool:
        with self._lock:
            return self._link is not None

    def current_port(self) -> str:
        with self._lock:
            return self._port if self._link is not None else ""

    def connect(self, port: str | None = None, auto: bool = True) -> str:
        with self._lock:
            if self._link is not None:
                if port and port != self._port:
                    self._close_locked()
                else:
                    return self._port
            target = (port or "").strip()
            if not target and auto:
                target = auto_detect_port()
            if not target:
                raise RuntimeError("No device found (auto-detect failed)")
            self._link = CdcLink(target)
            self._port = target
            return target

    def disconnect(self):
        with self._lock:
            self._close_locked()

    def run(self, fn: Callable[[CdcLink], T], *, port: str | None = None, auto: bool = True, retry: bool = True) -> T:
        with self._lock:
            link = self._ensure_link_locked(port=port, auto=auto)
            try:
                return fn(link)
            except Exception:
                self._close_locked()
                if not retry:
                    raise
                link = self._ensure_link_locked(port=port, auto=auto)
                return fn(link)

    def run_if_idle(self, fn: Callable[[CdcLink], T], *, port: str | None = None, auto: bool = True, retry: bool = True) -> T | None:
        # Non-blocking lock acquire for low-priority tasks like meter polling.
        if not self._lock.acquire(blocking=False):
            return None
        try:
            link = self._ensure_link_locked(port=port, auto=auto)
            try:
                return fn(link)
            except Exception:
                self._close_locked()
                if not retry:
                    raise
                link = self._ensure_link_locked(port=port, auto=auto)
                return fn(link)
        finally:
            self._lock.release()

    def _ensure_link_locked(self, *, port: str | None, auto: bool) -> CdcLink:
        if self._link is not None:
            if port and port != self._port:
                self._close_locked()
            else:
                return self._link
        target = (port or "").strip()
        if not target and auto:
            target = auto_detect_port()
        if not target:
            raise RuntimeError("No device found (auto-detect failed)")
        self._link = CdcLink(target)
        self._port = target
        return self._link

    def _close_locked(self):
        if self._link is not None:
            try:
                self._link.close()
            except Exception:
                pass
        self._link = None
        self._port = ""


_MANAGER = DeviceLinkManager()


def get_device_link_manager() -> DeviceLinkManager:
    return _MANAGER

