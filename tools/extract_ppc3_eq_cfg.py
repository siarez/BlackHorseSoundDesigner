#!/usr/bin/env python3
"""
Extract EQ register values from a PPC3 I2C command dump and emit them as JSONL.

This tool parses a PPC3-generated cfg file (sequence of I2C writes) and looks
up EQ register definitions (pages/subaddrs) from the TAS map JSONL. It then
collects the 4-byte values for all CH-LBQn/CH-RBQn coefficients (B0/B1/B2/A1/A2)
and prints one JSON object per register with the following fields:

  {
    "page": "0x..",           # page from the map (hex string)
    "subaddr": "0x..",        # subaddress from the map (hex string)
    "name": "CH-LBQ1B1",     # map entry name
    "bytes": 4,               # always 4 for EQ coefficients
    "value": "0x........",   # 32-bit value reconstructed from four writes
    "type": "LPF|HPF|Peaking|Unknown",   # when a full biquad is present
    "f0": <float Hz>,
    "q": <float>,
    "gain_db": <float>
  }

Inference fields (type/f0/q/gain_db) are added when all five registers for a
section (B0/B1/B2/A1/A2) are present; INTGAIN (BQ15) is not inferred.

Flags:
  --nondefault (or --non-default)
      Only print sections where at least one of the five registers differs from
      the map's default. When a section is selected, all five rows for that
      section are printed together (so you get the full biquad), rather than
      filtering individual rows.

Usage:
  python tools/extract_ppc3_eq_cfg.py [cfg_path] [map_jsonl] [--nondefault]

Defaults:
  cfg_path   = example_configs/ppc3_dump.cfg
  map_jsonl  = app/eqcore/maps/table11_pf5_from_lines_murgese.jsonl

Notes:
  - The cfg is interpreted as a stream of writes: "w 94 <addr> <value>".
    Register 0x7F selects the book (we look for book 0x8C). Register 0x00
    selects the page; subsequent writes are captured as bytes at (book,page,subaddr).
  - A1/A2 in PPC3/TAS are stored with opposite sign to the math form
    (register A1 = −a1, A2 = −a2). Inference converts them back internally for
    response evaluation; printed values remain as-captured from the cfg.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

# Import EQ core (no Qt deps)
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
from app.eqcore import SOS, default_freq_grid, sos_response_db, design_biquad, BiquadParams, FilterType


def load_map(jsonl_path: Path) -> list[dict]:
    rows = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if 'page' in obj and 'subaddr' in obj and 'name' in obj:
                rows.append(obj)
    return rows


def parse_cfg(cfg_path: Path) -> dict[tuple[int, int, int], int]:
    """Parse PPC3 I2C write cfg and return byte map keyed by (book,page,subaddr)."""
    book = None
    page = None
    mem: dict[tuple[int, int, int], int] = {}
    with cfg_path.open() as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            if parts[0].lower() != 'w' or parts[1].lower() != '94':
                continue
            try:
                addr = int(parts[2], 16)
                val = int(parts[3], 16)
            except Exception:
                continue
            if addr == 0x7F:
                book = val
                continue
            if addr == 0x00:
                page = val
                continue
            if book is None or page is None:
                continue
            mem[(book, page, addr)] = val & 0xFF
    return mem


def collect_eq(rows: list[dict]) -> list[dict]:
    eq_rows = []
    for r in rows:
        name = str(r.get('name', ''))
        if name.startswith('CH-LBQ') or name.startswith('CH-RBQ'):
            # Only 4-byte EQ coeffs
            try:
                if int(str(r.get('bytes', 4))) != 4:
                    continue
            except Exception:
                pass
            eq_rows.append(r)
    return eq_rows


def _to_s32(u: int) -> int:
    return u - 0x100000000 if (u & 0x80000000) else u


def _decode_coeffs(section: Dict[str, int]) -> Tuple[float, float, float, float, float] | None:
    """Decode 32-bit register ints to floats using app mapping and PPC3 sign convention.

    section: mapping tag->uint32 for tags B0,B1,B2,A1,A2
    Returns (b0,b1,b2,a1,a2) in math form (a1,a2 negated from registers).
    """
    try:
        b0 = _to_s32(section['B0']) / float(1 << 31)
        b1 = _to_s32(section['B1']) / float(1 << 30)
        b2 = _to_s32(section['B2']) / float(1 << 31)
        A1 = _to_s32(section['A1']) / float(1 << 30)
        A2 = _to_s32(section['A2']) / float(1 << 31)
    except Exception:
        return None
    a1 = -A1
    a2 = -A2
    return (b0, b1, b2, a1, a2)


def _estimate_fc_q(Hdb, f, fs, kind: str) -> Tuple[float | None, float | None]:
    """Estimate fc and Q by fitting around the -3 dB point using a small grid search."""
    n = len(Hdb)
    if kind == 'LPF':
        ref = float(sum(Hdb[: max(8, n//20)]) / max(8, n//20))
        target = ref - 3.0
        search = Hdb
        idx = None
        for i in range(1, n):
            if (search[i-1] - target) * (search[i] - target) <= 0:
                idx = i
                break
        if idx is None:
            return None, None
        f1, f2 = f[idx-1], f[idx]
        y1, y2 = Hdb[idx-1], Hdb[idx]
    else:  # HPF
        ref = float(sum(Hdb[-max(8, n//20):]) / max(8, n//20))
        target = ref - 3.0
        search = Hdb[::-1]
        idx = None
        for i in range(1, n):
            if (search[i-1] - target) * (search[i] - target) <= 0:
                idx = i
                break
        if idx is None:
            return None, None
        f1, f2 = f[-idx], f[-idx-1]
        y1, y2 = Hdb[-idx], Hdb[-idx-1]
    t = 0.0 if y2 == y1 else (target - y1) / (y2 - y1)
    fc = float(f1 * (f2 / f1) ** t)

    # refine Q and fc by small grid search
    q_grid = [0.3, 0.4, 0.5, 0.707, 0.9, 1.2, 1.6, 2.0, 2.5, 3.0]
    f_grid = [fc * m for m in (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)]
    best = (1e12, fc, 0.707)
    for f0 in f_grid:
        for q in q_grid:
            p = BiquadParams(typ=(FilterType.LPF if kind == 'LPF' else FilterType.HPF), fs=fs, f0=float(f0), q=float(q), gain_db=0.0)
            H = sos_response_db(design_biquad(p), f, fs)
            err = float(sum((H - Hdb) ** 2))
            if err < best[0]:
                best = (err, f0, q)
    return float(best[1]), float(best[2])


def _infer_params(sos: SOS, fs: float) -> Tuple[str, float | None, float | None, float | None]:
    """Infer basic type (LPF/HPF/Peaking), f0, Q, gain_db from SOS.

    Mirrors the lightweight logic from CoefCheckTab without Qt.
    """
    f = default_freq_grid(fs, n=2048, fmin=10.0)
    Hdb = sos_response_db(sos, f, fs)
    n = len(Hdb)
    low_avg = float(sum(Hdb[: max(8, n//20)]) / max(8, n//20))
    high_avg = float(sum(Hdb[-max(8, n//20):]) / max(8, n//20))
    near0 = lambda x: abs(x) < 1.5

    def _interp_fc(passband: str) -> float | None:
        if passband == 'low':
            ref = float(sum(Hdb[: max(8, n//20)]) / max(8, n//20))
            target = ref - 3.0
            search = Hdb
            idx = None
            for i in range(1, n):
                if (search[i-1] - target) * (search[i] - target) <= 0:
                    idx = i
                    break
            if idx is None:
                return None
            f1, f2 = f[idx-1], f[idx]
            y1, y2 = Hdb[idx-1], Hdb[idx]
        else:
            ref = float(sum(Hdb[-max(8, n//20):]) / max(8, n//20))
            target = ref - 3.0
            search = Hdb[::-1]
            idx = None
            for i in range(1, n):
                if (search[i-1] - target) * (search[i] - target) <= 0:
                    idx = i
                    break
            if idx is None:
                return None
            f1, f2 = f[-idx], f[-idx-1]
            y1, y2 = Hdb[-idx], Hdb[-idx-1]
        t = 0.0 if y2 == y1 else (target - y1) / (y2 - y1)
        return float(f1 * (f2 / f1) ** t)

    # LPF/HPF detection
    if near0(low_avg) and (high_avg < low_avg - 6.0):
        fc, q = _estimate_fc_q(Hdb, f, fs, 'LPF')
        return 'LPF', fc, q, 0.0
    if near0(high_avg) and (low_avg < high_avg - 6.0):
        fc, q = _estimate_fc_q(Hdb, f, fs, 'HPF')
        return 'HPF', fc, q, 0.0

    # Peaking: ends near 0 dB with midband deviation
    mid_idx = int(max(range(n), key=lambda i: abs(Hdb[i])))
    peak_db = float(Hdb[mid_idx])
    if near0(low_avg) and near0(high_avg) and abs(peak_db) > 0.75:
        # Initial estimates
        f0_init = float(f[mid_idx])
        target = peak_db - 3.0 if peak_db >= 0 else peak_db + 3.0
        i1 = None
        for i in range(mid_idx - 1, 1, -1):
            if (Hdb[i] - target) * (Hdb[i+1] - target) <= 0:
                i1 = i
                break
        i2 = None
        for i in range(mid_idx + 1, n - 2):
            if (Hdb[i] - target) * (Hdb[i+1] - target) <= 0:
                i2 = i
                break
        if i1 is not None and i2 is not None:
            def interp(i):
                f1, f2 = f[i], f[i+1]
                y1, y2 = Hdb[i], Hdb[i+1]
                t = 0.0 if y2 == y1 else (target - y1) / (y2 - y1)
                return float(f1 * (f2 / f1) ** t)
            fL = interp(i1)
            fR = interp(i2)
            bw = max(fR - fL, 1e-9)
            q_init = f0_init / bw
        else:
            q_init = 0.707

        # Refine by small grid search
        f_candidates = [f0_init * m for m in (0.9, 0.95, 1.0, 1.05, 1.1)]
        q_candidates = [max(0.2, q_init * m) for m in (0.5, 0.75, 1.0, 1.25, 1.5)]
        g_candidates = [peak_db + d for d in (-1.0, -0.5, 0.0, 0.5, 1.0)]
        best = (1e12, f0_init, q_init, peak_db)
        for ff in f_candidates:
            for qq in q_candidates:
                for gg in g_candidates:
                    p = BiquadParams(typ=FilterType.PEAK, fs=fs, f0=float(ff), q=float(qq), gain_db=float(gg))
                    H = sos_response_db(design_biquad(p), f, fs)
                    err = float(sum((H - Hdb) ** 2))
                    if err < best[0]:
                        best = (err, ff, qq, gg)
        _, f0, q, g = best
        return 'Peaking', float(f0), float(q), float(g)

    # Fallback: unknown
    return 'Unknown', None, None, None


def main(argv: list[str]) -> int:
    # Paths
    cfg_path = Path('example_configs/scale_detection/sample5.cfg')
    map_path = Path('app/eqcore/maps/table11_pf5_from_lines_murgese.jsonl')
    filter_nondefault = False
    # crude args: [script] [cfg] [map] [--nondefault]
    args = argv[1:]
    # recognize --nondefault / --non-default anywhere
    args_wo_flags = []
    for a in args:
        if a in ('--nondefault', '--non-default'):
            filter_nondefault = True
        else:
            args_wo_flags.append(a)
    if len(args_wo_flags) >= 1:
        cfg_path = Path(args_wo_flags[0])
    if len(args_wo_flags) >= 2:
        map_path = Path(args_wo_flags[1])
    if not cfg_path.exists():
        print(f'Config not found: {cfg_path}', file=sys.stderr)
        return 2
    if not map_path.exists():
        print(f'Map not found: {map_path}', file=sys.stderr)
        return 2

    rows = load_map(map_path)
    eq_rows = collect_eq(rows)
    mem = parse_cfg(cfg_path)

    # Book for TAS EQ is 0x8C per PPC3
    BOOK_TARGET = 0x8C

    # Build per-section aggregates to enable inference
    sections_by_base: Dict[str, Dict[str, int]] = {}
    # Also maintain list of row outputs to enrich with inference fields
    # First pass: determine which bases have any non-default value (if filtering)
    changed_bases = set()
    for r in eq_rows:
        name = str(r.get('name'))
        base = name[:-2] if len(name) > 2 else name
        page_hex = str(r.get('page'))
        sub_hex = str(r.get('subaddr'))
        try:
            page = int(page_hex, 16)
            subaddr = int(sub_hex, 16)
        except Exception:
            continue
        b0 = mem.get((BOOK_TARGET, page, subaddr), 0)
        b1 = mem.get((BOOK_TARGET, page, subaddr + 1), 0)
        b2 = mem.get((BOOK_TARGET, page, subaddr + 2), 0)
        b3 = mem.get((BOOK_TARGET, page, subaddr + 3), 0)
        value = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        try:
            dflt_hex = str(r.get('default', '0x00000000'))
            dflt_val = int(dflt_hex, 16)
        except Exception:
            dflt_val = None
        if filter_nondefault:
            if dflt_val is None or value != dflt_val:
                changed_bases.add(base)

    out = []
    for r in eq_rows:
        page_hex = str(r.get('page'))
        sub_hex = str(r.get('subaddr'))
        # Parse hex like '0x1A'
        try:
            page = int(page_hex, 16)
            subaddr = int(sub_hex, 16)
        except Exception:
            continue
        # Read 4 bytes starting at subaddr
        b0 = mem.get((BOOK_TARGET, page, subaddr), 0)
        b1 = mem.get((BOOK_TARGET, page, subaddr + 1), 0)
        b2 = mem.get((BOOK_TARGET, page, subaddr + 2), 0)
        b3 = mem.get((BOOK_TARGET, page, subaddr + 3), 0)
        value = (b0 << 24) | (b1 << 16) | (b2 << 8) | b3
        # If filtering defaults, include all 5 rows of a section when at least one differs
        if filter_nondefault:
            name = str(r.get('name'))
            base = name[:-2] if len(name) > 2 else name
            if base not in changed_bases:
                continue
        # Record into section bucket
        name = str(r.get('name'))
        base = name[:-2] if len(name) > 2 else name
        tag = name[-2:] if len(name) >= 2 else ''
        bucket = sections_by_base.setdefault(base, {})
        if tag in ('B0', 'B1', 'B2', 'A1', 'A2'):
            bucket[tag] = value

        obj = {
            'page': f'0x{page:02X}',
            'subaddr': f'0x{subaddr:02X}',
            'name': name,
            'bytes': 4,
            'value': f'0x{value:08X}',
        }
        out.append(obj)

    # Compute inference per complete section (skip INTGAIN BQ15)
    infer: Dict[str, dict] = {}
    FS = 48000.0
    for base, sect in sections_by_base.items():
        # base like CH-LBQ1, CH-RBQ14, CH-LBQ15 (intgain)
        try:
            idx = int(''.join(ch for ch in base if ch.isdigit()))
        except Exception:
            idx = 0
        if idx == 15:
            continue
        if all(k in sect for k in ('B0', 'B1', 'B2', 'A1', 'A2')):
            coeffs = _decode_coeffs(sect)
            if coeffs is None:
                continue
            sos = SOS(*coeffs)
            kind, f0, q, g = _infer_params(sos, FS)
            infer[base] = {
                'type': kind,
                'f0': round(f0, 2) if f0 is not None else None,
                'q': round(q, 2) if q is not None else None,
                'gain_db': round(g, 2) if g is not None else None,
            }

    # Print as JSONL, enriching with inference where available
    for o in out:
        base = o['name'][:-2] if len(o['name']) > 2 else o['name']
        if base in infer:
            o.update(infer[base])
        print(json.dumps(o))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
