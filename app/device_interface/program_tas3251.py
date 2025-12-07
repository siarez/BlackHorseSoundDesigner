#!/usr/bin/env python3
"""
Program TAS3251 non-coefficient registers via MCU journal (!jwrb).

Sends two separate records:
- type 0x51 id 0x01 -> shabrang_tas_program_memory.jsonl
- type 0x51 id 0x02 -> shabrang_tas_register_tuning.jsonl

Payload format (consistent with ES9821 helper):
- Byte 0: 7-bit I2C address (default 0x4A; override with --addr)
- Then pairs: [reg, val] for each JSONL row in order
  - JSONL schema: simple-reg-v1 with fields [addr, value, comment]

Usage:
  uv run -m app.device_interface.program_tas3251 \
      --program bh_app/app/eqcore/maps/shabrang_tas_program_memory.jsonl \
      --tuning  bh_app/app/eqcore/maps/shabrang_tas_register_tuning.jsonl \
      [--addr 0x4A] [--port <SERIAL>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

from .cdc_link import CdcLink, auto_detect_port


def _parse_byte(x: str | int) -> int:
    if isinstance(x, int):
        v = x
    else:
        v = int(str(x), 0)
    if v < 0 or v > 0xFF:
        raise ValueError(f"byte out of range: {x}")
    return v


def load_simple_regs(jsonl_path: Path) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith('//'):
                continue
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError:
                print(f'Skipping {ln} could not be parsed')
            if isinstance(obj, dict) and obj.get("type") == "meta":
                continue
            addr = _parse_byte(obj.get("addr"))
            val = _parse_byte(obj.get("value"))
            pairs.append((addr, val))
    return pairs


def build_payload_tas3251(pairs: List[Tuple[int, int]], i2c_addr_7bit: int) -> bytes:
    if i2c_addr_7bit < 0 or i2c_addr_7bit > 0x7F:
        raise ValueError("I2C 7-bit address must be in 0..0x7F")
    out = bytearray()
    out.append(i2c_addr_7bit & 0x7F)
    for a, v in pairs:
        out.append(a & 0xFF)
        out.append(v & 0xFF)
    return bytes(out)


def send_record(link: CdcLink, typ: int, _id: int, payload: bytes) -> bool:
    ok, lines = link.jwrb_with_log(typ, _id, payload)
    status = "OK" if ok else "ERR"
    print(f"[{status}] jwrb type=0x{typ:02X} id=0x{_id:02X} len={len(payload)}")
    # Print any APPLY lines
    applies = [ln for ln in lines if ln.startswith("OK APPLY") or ln.startswith("ERR APPLY")]
    for ln in applies:
        print(ln)
    return ok


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Send TAS3251 non-coefficient registers as journal records")
    ap.add_argument("--program", type=Path, default=Path("app/eqcore/maps/shabrang_tas_program_memory.jsonl"),
                    help="Path to program memory JSONL")
    ap.add_argument("--tuning", type=Path, default=Path("app/eqcore/maps/shabrang_tas_register_tuning.jsonl"),
                    help="Path to register tuning JSONL")
    ap.add_argument("--addr", type=lambda s: int(s, 0), default=0x4A, help="TAS3251 7-bit I2C addr (default 0x4A)")
    ap.add_argument("--port", "-p", help="Serial port (auto-detect if omitted)")

    args = ap.parse_args(argv)

    if not args.program.exists():
        print(f"Program JSONL not found: {args.program}", file=sys.stderr)
        return 2
    if not args.tuning.exists():
        print(f"Tuning JSONL not found: {args.tuning}", file=sys.stderr)
        return 2
    if args.addr < 0 or args.addr > 0x7F:
        print(f"Invalid I2C 7-bit address: {args.addr:#x}", file=sys.stderr)
        return 2

    prog_pairs = load_simple_regs(args.program)
    tune_pairs = load_simple_regs(args.tuning)
    if not prog_pairs:
        print("Program JSONL contained no pairs", file=sys.stderr)
        return 3
    if not tune_pairs:
        print("Tuning JSONL contained no pairs", file=sys.stderr)
        return 3

    prog_payload = build_payload_tas3251(prog_pairs, args.addr)
    tune_payload = build_payload_tas3251(tune_pairs, args.addr)

    print(f"Built TAS3251 program payload: {len(prog_pairs)} regs -> {len(prog_payload)} bytes (addr=0x{args.addr:02X})")
    print(f"Built TAS3251 tuning  payload: {len(tune_pairs)} regs -> {len(tune_payload)} bytes (addr=0x{args.addr:02X})")

    port = args.port or auto_detect_port()
    if not port:
        print("Serial port not specified and auto-detect failed. Use --port.", file=sys.stderr)
        return 6
    print(f"Using port: {port}")

    link: CdcLink | None = None
    try:
        link = CdcLink(port)
        ok1 = send_record(link, 0x51, 0x01, prog_payload)
        ok2 = send_record(link, 0x51, 0x02, tune_payload)
        return 0 if (ok1 and ok2) else 7
    finally:
        if link is not None:
            link.close()


if __name__ == "__main__":
    raise SystemExit(main())

