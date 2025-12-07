#!/usr/bin/env python3
"""
Program ES9821 via MCU journal (!jwrb) over USB CDC.

Input
- JSONL register map similar to app/eqcore/maps/es9821_registers.jsonl
  Each non-meta line should include at least: {"addr": "0xNN", "reset": "0bxxxxxxxx" | ""}

Payload (ES9821-specific v1)
- Byte 0: 7-bit I2C device address (0x40 by default)
- Then repeated pairs: [reg_addr (1B), value (1B)] in ascending register order
- For reset patterns with 'x' bits, 'x' is treated as 0 (per requirement)
- Empty/missing reset entries are skipped

The resulting payload length must be <= 320 bytes (journal max).

Usage
  uv run -m app.device_interface.program_es9821 \
      --jsonl app/eqcore/maps/es9821_registers.jsonl \
      --port /dev/tty.usbmodemXXXX

Options
- --type/--id to override journal type/id (defaults 0x21/0x00)
- --addr to override ES9821 7-bit I2C address (default 0x40)
- --dry-run to print summary without sending
- --out to save the binary payload to a file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

from .cdc_link import CdcLink, auto_detect_port, DEFAULT_BAUD, DEFAULT_TIMEOUT


# -------------------- JSONL parsing --------------------

def _parse_reset_to_byte(reset: str) -> int | None:
    """Parse reset field to an 8-bit integer.

    Accepts forms like "0b01100100", "0b0xxxx000" (x -> 0), "0xNN", or decimal.
    Returns None if reset is empty or cannot be parsed.
    """
    if not reset:
        return None
    s = reset.strip()
    try:
        if s.startswith("0b") or s.startswith("0B"):
            bits = s[2:].replace("x", "0").replace("X", "0")
            if not bits or any(c not in "01" for c in bits):
                return None
            v = int(bits, 2)
        elif s.startswith("0x") or s.startswith("0X"):
            v = int(s, 16)
        else:
            # allow decimal strings
            v = int(s, 10)
    except Exception:
        return None
    if v < 0 or v > 0xFF:
        return None
    return v


def _parse_addr(addr: str | int) -> int | None:
    """Parse address field to an 8-bit register address."""
    if isinstance(addr, int):
        v = addr
    else:
        try:
            v = int(addr, 0)
        except Exception:
            return None
    if v < 0 or v > 0xFF:
        return None
    return v


def load_es9821_pairs(jsonl_path: Path) -> List[Tuple[int, int]]:
    """Load (reg, value) pairs from ES9821 JSONL mapping.

    - Skips meta lines (type == "meta").
    - Skips entries with empty or unparsable reset.
    - Coerces 'x' bits to 0 for binary resets.
    - Sorts by register address.
    """
    pairs: List[Tuple[int, int]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('//'):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f'Skipping {line} could not be parsed')
            if isinstance(obj, dict) and obj.get("type") == "meta":
                continue
            addr = _parse_addr(obj.get("addr"))
            reset_raw = obj.get("reset", "")
            val = _parse_reset_to_byte(reset_raw)
            if addr is None or val is None:
                # Skip entries without usable address or reset value
                continue
            pairs.append((addr, val))
    # sort by address, stable
    # pairs.sort(key=lambda t: t[0])
    return pairs


# -------------------- Payload builder --------------------

def build_payload_es9821(pairs: Iterable[Tuple[int, int]], i2c_addr_7bit: int = 0x40) -> bytes:
    """Construct ES9821-specific payload:
    [i2c_addr_7bit] + (reg, val)*
    """
    if i2c_addr_7bit < 0 or i2c_addr_7bit > 0x7F:
        raise ValueError("I2C 7-bit address must be in 0..0x7F")
    data = bytearray()
    data.append(i2c_addr_7bit & 0x7F)
    for reg, val in pairs:
        data.append(reg & 0xFF)
        data.append(val & 0xFF)
    return bytes(data)


# -------------------- CLI --------------------

def auto_detect_port() -> str:
    """Pick the first port matching our product/manufacturer or VID/PID.

    Prefers:
      - manufacturer contains "Black Horse Audio" OR product contains "Shabrang"
      - fallback: VID 0x0483 and PID 0x5740 (ST CDC ACM default in this project)
      - last resort: description contains CDC/ACM/STM32
    """
    try:
        from serial.tools import list_ports
    except Exception:
        return ""

    ports = list(list_ports.comports())
    if not ports:
        return ""

    def match_primary(p) -> bool:
        man = (p.manufacturer or "").lower()
        prod = (p.product or "").lower()
        return ("black horse audio" in man) or ("shabrang" in prod)

    # Primary: explicit strings
    for p in ports:
        if match_primary(p):
            return p.device

    # Fallback: VID/PID (0x0483, 0x5740)
    for p in ports:
        try:
            if (p.vid == 0x0483) and (p.pid == 0x5740):
                return p.device
        except Exception:
            pass

    # Last resort: generic CDC/ACM hints
    for p in ports:
        desc = ((p.description or "") + " " + (p.manufacturer or "") + " " + (p.product or "")).lower()
        if any(tag in desc for tag in ["cdc", "acm", "stm32", "usb serial", "ux_device_cdc_acm"]):
            return p.device

    return ""

def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert ES9821 JSONL to journal payload and send via CDC !jwrb")
    ap.add_argument("--jsonl", required=True, type=Path, help="Path to es9821_registers.jsonl")
    ap.add_argument("--port", "-p", help="Serial port (e.g., /dev/tty.usbmodemXXXX)")
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x20, help="ES9821 7-bit I2C addr (default 0x20; 8-bit write is 0x40)")
    ap.add_argument("--type", type=lambda s: int(s, 0), default=0x21, help="Journal type (default 0x21)")
    ap.add_argument("--id", type=lambda s: int(s, 0), default=0x00, help="Journal id (default 0x00)")
    ap.add_argument("--out", type=Path, help="Optional output file to write binary payload")
    ap.add_argument("--dry-run", action="store_true", help="Build payload and print summary; do not send")

    args = ap.parse_args(argv)

    if not args.jsonl.exists():
        print(f"JSONL not found: {args.jsonl}", file=sys.stderr)
        return 2

    # Validate 7-bit address
    if args.addr < 0x00 or args.addr > 0x7F:
        print(f"Invalid I2C 7-bit address: {args.addr:#x}", file=sys.stderr)
        return 2

    pairs = load_es9821_pairs(args.jsonl)
    if not pairs:
        print("No usable (addr, reset) entries found in JSONL", file=sys.stderr)
        return 3

    payload = build_payload_es9821(pairs, i2c_addr_7bit=args.addr)
    if len(payload) > 320:
        print(f"Payload too large ({len(payload)} bytes) exceeds 320-byte journal limit", file=sys.stderr)
        return 4

    # Optional output file
    if args.out:
        try:
            args.out.write_bytes(payload)
        except Exception as e:
            print(f"Failed to write payload to {args.out}: {e}", file=sys.stderr)
            return 5

    print(f"Built ES9821 payload: {len(pairs)} regs -> {len(payload)} bytes (addr=0x{args.addr:02X})")
    if args.dry_run:
        return 0

    # Auto-detect port if not provided
    port = args.port
    if not port:
        port = auto_detect_port()
        if not port:
            print("Serial port not specified and auto-detect failed. Use --port.", file=sys.stderr)
            return 6
        else:
            print(f"Auto-detected port: {port}")

    # Send via CDC !jwrb
    link = None
    try:
        link = CdcLink(port)
        ok, pre_lines = link.jwrb_with_log(args.type, args.id, payload)
        if not ok:
            print("Failed to write journal payload (jwrb)", file=sys.stderr)
            return 7
        print("OK: journal write committed (OK JWR)")
        # Try to read any apply-status lines emitted by firmware
        applies = [ln for ln in pre_lines if ln.startswith("OK APPLY") or ln.startswith("ERR APPLY")]
        if not applies:
            post_lines = link.read_lines(1.0)
            applies = [ln for ln in post_lines if ln.startswith("OK APPLY") or ln.startswith("ERR APPLY")]
        if applies:
            for ln in applies:
                print(ln)
        else:
            # Optional: print any other lines for debugging
            pass
        return 0
    finally:
        if link is not None:
            link.close()


if __name__ == "__main__":
    raise SystemExit(main())
