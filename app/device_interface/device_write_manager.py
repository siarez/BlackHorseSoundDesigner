from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .device_link_manager import get_device_link_manager


@dataclass(frozen=True)
class JournalWrite:
    typ: int
    rec_id: int
    payload: bytes
    label: str = ""


@dataclass
class JournalWriteResult:
    attempted: int = 0
    succeeded: int = 0
    failed: list[str] = field(default_factory=list)
    apply_logs: list[str] = field(default_factory=list)
    lines_by_label: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


def build_i2c32_payload(items: Iterable[tuple[int, int, int]], i2c7: int = 0x4A) -> bytes:
    """Build a compact 32-bit write stream for !jwrb payloads.

    Item format: (page, subaddr, value_u32)
    Encoded format: [i2c7] + repeated { [0xFD, page] on page changes, [0x80|sub, b3, b2, b1, b0] }.
    """
    payload = bytearray()
    payload.append(i2c7 & 0xFF)
    cur_page = None
    for page_i, sub_i, val_u32 in items:
        if cur_page != page_i:
            payload.append(0xFD)
            payload.append(page_i & 0xFF)
            cur_page = page_i
        payload.append(0x80 | (sub_i & 0x7F))
        payload.append((val_u32 >> 24) & 0xFF)
        payload.append((val_u32 >> 16) & 0xFF)
        payload.append((val_u32 >> 8) & 0xFF)
        payload.append(val_u32 & 0xFF)
    return bytes(payload)


class DeviceWriteManager:
    """Centralized journal writer for coefficient + sidecar updates."""

    def __init__(self):
        self._link_mgr = get_device_link_manager()

    def apply(
        self,
        writes: Sequence[JournalWrite],
        *,
        port: str | None = None,
        auto: bool = True,
        retry: bool = True,
    ) -> JournalWriteResult:
        normalized = [w for w in writes if isinstance(w.payload, (bytes, bytearray)) and len(w.payload) > 0]
        if not normalized:
            return JournalWriteResult()

        def _send_all(link) -> JournalWriteResult:
            out = JournalWriteResult()
            for w in normalized:
                label = w.label or f"type={w.typ:#x} id={w.rec_id:#x}"
                ok, lines = link.jwrb_with_log(w.typ, w.rec_id, bytes(w.payload))
                out.attempted += 1
                out.lines_by_label[label] = lines
                applies = [ln for ln in lines if ln.startswith("OK APPLY") or ln.startswith("ERR APPLY")]
                out.apply_logs.extend(f"[{label}] {ln}" for ln in applies)
                if ok:
                    out.succeeded += 1
                else:
                    out.failed.append(label)
            return out

        return self._link_mgr.run(_send_all, port=port, auto=auto, retry=retry)


_WRITER = DeviceWriteManager()


def get_device_write_manager() -> DeviceWriteManager:
    return _WRITER

