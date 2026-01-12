from __future__ import annotations

"""
Compact sidecar binary pack/unpack for app UI state (journal type 0x53).

Formats (little-endian fields where multi-byte):

EQ (REC_STATE_EQ = 0x90):
  [ver u8=1][fs_u16][count u8]
  repeat count times:
    [type u8][f0_u16][q_u8][gain_qdb_i8]

XO (REC_STATE_XO = 0x91):
  [ver u8=1][fs_u16][cntA u8][cntB u8]
  A rows: repeat cntA: [mode u8][topo u8][f0_u16][q_u8][rip_u8]
  B rows: repeat cntB: [mode u8][topo u8][f0_u16][q_u8][rip_u8]
  Misc: [flags u8][delayA u8][delayB u8][gainA_qdb_i8][gainB_qdb_i8]
    flags: bit0 invertA, bit1 invertB

MIXER (REC_STATE_MIXER = 0x92):
  [ver u8=1][n u8=4] then 4x i16 (Q9.7) in order:
    LefttoLeft, RighttoLeft, LefttoRight, RighttoRight

MIX/GAIN (REC_STATE_MIXGAIN = 0x93):
  [ver u8=1][n u8] then n x i16 (Q9.7) in fixed name order provided by caller

XBAR (REC_STATE_XBAR = 0x94):
  [ver u8=1][n u8] then n x i16 (Q9.7) in fixed name order provided by caller
"""

from typing import List, Dict, Tuple
import math


# ---- Common helpers ----

def _clampf(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _f0_to_u16_hz(f0: float) -> int:
    return int(max(0, min(65535, round(float(f0)))))


def _u16_to_int(b0: int, b1: int) -> int:
    return (b1 << 8) | b0


def _int_to_u16_le(v: int) -> Tuple[int, int]:
    v &= 0xFFFF
    return (v & 0xFF), ((v >> 8) & 0xFF)


def _q_to_u8(q: float, q_min: float = 0.1, q_max: float = 10.0) -> int:
    qc = _clampf(float(q), q_min, q_max)
    # Map log10 space from [log10(q_min), log10(q_max)] -> [0,255]
    y = (math.log10(qc) - math.log10(q_min)) / (math.log10(q_max) - math.log10(q_min))
    code = int(round(_clampf(y, 0.0, 1.0) * 255.0))
    return code


def _u8_to_q(code: int, q_min: float = 0.1, q_max: float = 10.0) -> float:
    y = max(0, min(255, int(code))) / 255.0
    logq = math.log10(q_min) + y * (math.log10(q_max) - math.log10(q_min))
    return 10.0 ** logq


def _db_to_i8_q25(db: float, lo: float = -24.0, hi: float = 24.0) -> int:
    d = _clampf(float(db), lo, hi)
    v = int(round(d * 4.0))
    if v < -128:
        v = -128
    if v > 127:
        v = 127
    return v & 0xFF


def _i8_q25_to_db(b: int) -> float:
    v = b if b < 128 else b - 256
    return float(v) / 4.0


def _lin_to_i16_q9_7(x: float) -> Tuple[int, int]:
    # Q9.7: 7 fractional bits => scale by 128, clamp to int16
    s = int(round(float(x) * 128.0))
    if s < -32768:
        s = -32768
    if s > 32767:
        s = 32767
    s &= 0xFFFF
    return (s & 0xFF), ((s >> 8) & 0xFF)


def _i16_q9_7_to_lin(b0: int, b1: int) -> float:
    v = ((b1 << 8) | b0)
    if v & 0x8000:
        v = v - 0x10000
    return float(v) / 128.0


def _ripple_to_u8(rip_db: float) -> int:
    # Map 0..3.0 dB -> 0..255
    r = _clampf(float(rip_db), 0.0, 3.0)
    return int(round(r / 3.0 * 255.0)) & 0xFF


def _u8_to_ripple(b: int) -> float:
    return (max(0, min(255, int(b))) / 255.0) * 3.0


# ---- Domain mappings (UI text ↔ code) ----

EQ_TYPE_TEXTS: List[str] = [
    "Peak (Peaking EQ)",
    "Low Shelf",
    "High Shelf",
    "Low-pass",
    "High-pass",
    "Band-pass (const peak)",
    "Notch",
    "All-pass (Unity)",
    "All-pass 1st (Phase)",
    "All-pass 2nd (Phase)",
]

XO_MODE_TEXTS: List[str] = [
    "All-pass",
    "Phase shift 1st",
    "Phase shift 2nd",
    "Low-pass",
    "High-pass",
    "Peaking EQ",
]

XO_TOPO_TEXTS: List[str] = [
    "Butterworth 1st",
    "Butterworth 2nd",
    "Bessel",
    "Chebyshev I",
    "Variable Q 2nd",
]


# ---- EQ ----

def pack_eq_state(eq_items: List[Dict], fs_hz: int = 48000) -> bytes:
    n = min(255, len(eq_items))
    out = bytearray()
    out.append(1)  # ver
    out.extend(_int_to_u16_le(int(fs_hz)))
    out.append(n & 0xFF)
    for i in range(n):
        ent = eq_items[i] or {}
        t = ent.get("type", "")
        try:
            tcode = EQ_TYPE_TEXTS.index(t)
        except ValueError:
            tcode = 0
        f0 = _f0_to_u16_hz(ent.get("f0", 1000.0))
        q8 = _q_to_u8(ent.get("q", 0.707))
        g8 = _db_to_i8_q25(ent.get("gain_db", 0.0))
        out.extend([tcode & 0xFF, *_int_to_u16_le(f0), q8 & 0xFF, g8 & 0xFF])
    return bytes(out)


def unpack_eq_state(data: bytes) -> Dict:
    if not data or len(data) < 4:
        return {"fs": 48000, "eq": []}
    ver = data[0]
    fs = _u16_to_int(data[1], data[2])
    n = data[3]
    eq: List[Dict] = []
    idx = 4
    for _ in range(n):
        if idx + 5 > len(data):
            break
        tcode = data[idx]; f0 = _u16_to_int(data[idx+1], data[idx+2]); q8 = data[idx+3]; g8 = data[idx+4]
        idx += 5
        ttext = EQ_TYPE_TEXTS[tcode] if 0 <= tcode < len(EQ_TYPE_TEXTS) else EQ_TYPE_TEXTS[0]
        eq.append({
            "type": ttext,
            "f0": float(f0),
            "q": _u8_to_q(q8),
            "gain_db": _i8_q25_to_db(g8),
        })
    return {"fs": fs, "eq": eq}


# ---- XO ----

def pack_xo_state(xo: Dict, fs_hz: int = 48000) -> bytes:
    A = xo.get("A", []) or []
    B = xo.get("B", []) or []
    out = bytearray()
    out.append(1)
    out.extend(_int_to_u16_le(int(fs_hz)))
    out.append(min(255, len(A)) & 0xFF)
    out.append(min(255, len(B)) & 0xFF)
    def _row(ent: Dict) -> List[int]:
        m = ent.get("mode", ""); t = ent.get("topology", "")
        try:
            mcode = XO_MODE_TEXTS.index(m)
        except ValueError:
            mcode = 0
        try:
            tcode = XO_TOPO_TEXTS.index(t)
        except ValueError:
            tcode = 0
        f0 = _f0_to_u16_hz(ent.get("f0", 2000.0))
        q8 = _q_to_u8(ent.get("q", 0.707))
        r8 = _ripple_to_u8(ent.get("ripple_db", 0.5))
        b0, b1 = _int_to_u16_le(f0)
        return [mcode & 0xFF, tcode & 0xFF, b0, b1, q8 & 0xFF, r8 & 0xFF]
    for ent in A:
        out.extend(_row(ent))
    for ent in B:
        out.extend(_row(ent))
    misc = xo.get("misc", {}) or {}
    flags = (1 if misc.get("invertA") else 0) | ((1 if misc.get("invertB") else 0) << 1)
    out.append(flags & 0xFF)
    out.append(int(misc.get("delayA", 0)) & 0xFF)
    out.append(int(misc.get("delayB", 0)) & 0xFF)
    out.append(_db_to_i8_q25(misc.get("gainA_db", 0.0)) & 0xFF)
    out.append(_db_to_i8_q25(misc.get("gainB_db", 0.0)) & 0xFF)
    return bytes(out)


def unpack_xo_state(data: bytes) -> Dict:
    if not data or len(data) < 6:
        return {"fs": 48000, "A": [], "B": [], "misc": {}}
    fs = _u16_to_int(data[1], data[2])
    cntA = data[3]; cntB = data[4]
    idx = 5
    def _read_rows(n: int) -> List[Dict]:
        nonlocal idx
        rows: List[Dict] = []
        for _ in range(n):
            if idx + 6 > len(data):
                break
            mcode = data[idx]; tcode = data[idx+1]
            f0 = _u16_to_int(data[idx+2], data[idx+3])
            q8 = data[idx+4]; r8 = data[idx+5]
            idx += 6
            mtxt = XO_MODE_TEXTS[mcode] if 0 <= mcode < len(XO_MODE_TEXTS) else XO_MODE_TEXTS[0]
            ttxt = XO_TOPO_TEXTS[tcode] if 0 <= tcode < len(XO_TOPO_TEXTS) else XO_TOPO_TEXTS[0]
            rows.append({"mode": mtxt, "topology": ttxt, "f0": float(f0), "q": _u8_to_q(q8), "ripple_db": _u8_to_ripple(r8)})
        return rows
    A = _read_rows(cntA)
    B = _read_rows(cntB)
    misc = {}
    if idx + 5 <= len(data):
        flags = data[idx]; idx += 1
        misc["invertA"] = bool(flags & 0x01)
        misc["invertB"] = bool(flags & 0x02)
        misc["delayA"] = int(data[idx]); misc["delayB"] = int(data[idx+1]); idx += 2
        misc["gainA_db"] = _i8_q25_to_db(data[idx]); misc["gainB_db"] = _i8_q25_to_db(data[idx+1]); idx += 2
    return {"fs": fs, "A": A, "B": B, "misc": misc}


# ---- Simple Q9.7 vector payloads (Mixer, MixGain, Xbar) ----

def pack_q97_values(order: List[str], values: Dict[str, float]) -> bytes:
    out = bytearray()
    out.append(1)
    out.append(len(order) & 0xFF)
    for name in order:
        v = float(values.get(name, 0.0))
        b0, b1 = _lin_to_i16_q9_7(v)
        out.extend([b0, b1])
    return bytes(out)


def unpack_q97_values(data: bytes, order: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not data or len(data) < 2:
        return out
    n = data[1]
    idx = 2
    for i in range(min(n, len(order))):
        if idx + 2 > len(data):
            break
        out[order[i]] = _i16_q9_7_to_lin(data[idx], data[idx+1])
        idx += 2
    return out

