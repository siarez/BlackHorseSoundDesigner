from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Iterable

from PySide6 import QtWidgets

from .crossover_tab import CrossoverTab
from .eq_tab import EqTab
from app.eqcore import design_biquad
from .util import q_to_hex_twos


def _hex_u32(n: int) -> str:
    n = int(n) & 0xFFFFFFFF
    return f"0x{n:08X}"


def export_pf5_from_ui(parent: QtWidgets.QWidget, xo: CrossoverTab,
                       ref_jsonl: Path | str = Path('app/eqcore/maps/shabrang_tas3261.jsonl'),
                       out_dir: Path | str = Path('app/exports')) -> Path | None:
    """Export a PF5 JSONL by overlaying UI values onto the reference map.

    Current behavior:
      - CROSS OVER BQs: populate BQ1..BQ5 using Crossover Channel A.
      - SUB CROSS OVER BQs: populate BQ1..BQ5 using Crossover Channel B.
      - PHASE OPTIMIZER: Delay Left/Right = Channel A; Delay Sub = Channel B
      - EQ LEFT 14 BQs and EQ RIGHT 14 BQs: populate 14 biquads from the EQ tab
        (same values to left and right by request), using hardware‑mapped scaling
        (a0=1 with stage gain).
      - LEFT INTGAIN BQ and RIGHT INTGAIN BQ: populate Stage Gain (BQ15) from EQ tab.
      - All other rows are copied as-is from the reference file.

    Returns the output path on success; None on failure.
    """
    ref_path = Path(ref_jsonl)
    if not ref_path.exists():
        QtWidgets.QMessageBox.critical(parent, 'Export', f'Reference JSONL not found: {ref_path}')
        return None

    out_base = Path(out_dir)
    out_base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out_path = out_base / f'pf5_export_{ts}.jsonl'

    # Precompute Channel A/B crossover sections (rows 0..4)
    sections_A = []
    for row in range(xo.table_xo_A.rowCount()):
        invert_this = xo.chk_xo_pol_A.isChecked() and (row == 0)
        sections_A.append(xo._design_xo_biquad(xo.table_xo_A, row, invert_polarity=invert_this))
    sections_B = []
    for row in range(xo.table_xo_B.rowCount()):
        invert_this = xo.chk_xo_pol_B.isChecked() and (row == 0)
        sections_B.append(xo._design_xo_biquad(xo.table_xo_B, row, invert_polarity=invert_this))

    # Delays (Channel A/B)
    delay_A = int(getattr(xo, 'spin_delay_A', None).value() if hasattr(xo, 'spin_delay_A') else 0)
    delay_B = int(getattr(xo, 'spin_delay_B', None).value() if hasattr(xo, 'spin_delay_B') else 0)

    # Channel gains (dB -> linear) for OUTPUT CROSS BAR mapping
    gain_A_db = float(getattr(xo, 'spin_gain_A', None).value()) if hasattr(xo, 'spin_gain_A') else 0.0
    gain_B_db = float(getattr(xo, 'spin_gain_B', None).value()) if hasattr(xo, 'spin_gain_B') else 0.0
    gain_A_lin = 10.0 ** (gain_A_db/20.0)
    gain_B_lin = 10.0 ** (gain_B_db/20.0)

    # Gather EQ mapped sections (14 + stage) from the EQ tab if present
    eq = getattr(parent, 'eq_tab', None)
    eq_sections = []
    eq_stage = (1.0, 0.0, 0.0, 0.0, 0.0)
    if isinstance(eq, EqTab):
        n = eq.table.rowCount()
        G = 1.0
        for row in range(n):
            p = eq._params_from_row(row)
            sos = design_biquad(p)
            Si = max(abs(sos.b0), abs(sos.b1) / 2.0, abs(sos.b2))
            b0 = sos.b0 / Si
            b1 = sos.b1 / Si
            b2 = sos.b2 / Si
            a1 = sos.a1
            a2 = sos.a2
            G *= Si
            eq_sections.append((b0, b1, b2, a1, a2))
        eq_stage = (G, 0.0, 0.0, 0.0, 0.0)

    # Input mixer values (Q9.23) from the Input Mixer tab
    mixer = getattr(parent, 'mixer_tab', None)
    mixer_hex = mixer.values_hex() if hasattr(mixer, 'values_hex') else {}

    # Stream parse and write
    current_section = None
    try:
        with ref_path.open() as fin, out_path.open('w') as fout:
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get('type') == 'section':
                    current_section = obj.get('title') or current_section
                    # pass section through
                    fout.write(json.dumps(obj) + '\n')
                    continue

                # It's a row; decide if we overlay
                name = str(obj.get('name', ''))
                fmt = str(obj.get('format', ''))
                default = obj.get('default')

                replaced = False
                # Helper to set b/a fields with proper Q format
                def _set_coef(obj, tag: str, vals: tuple[float, float, float, float, float], stage: bool = False):
                    b0, b1, b2, a1, a2 = vals
                    if stage:
                        if tag == 'B0': obj['default'] = q_to_hex_twos(b0, 27); return True
                        if tag == 'B1': obj['default'] = q_to_hex_twos(b1, 26); return True
                        if tag == 'B2': obj['default'] = q_to_hex_twos(b2, 27); return True
                        # Denominator uses TI convention -a1,-a2
                        if tag == 'A1': obj['default'] = q_to_hex_twos(-a1, 30); return True
                        if tag == 'A2': obj['default'] = q_to_hex_twos(-a2, 31); return True
                        return False
                    else:
                        if tag == 'B0': obj['default'] = q_to_hex_twos(b0, 31); return True
                        if tag == 'B1': obj['default'] = q_to_hex_twos(b1, 30); return True
                        if tag == 'B2': obj['default'] = q_to_hex_twos(b2, 31); return True
                        # Denominator uses TI convention -a1,-a2
                        if tag == 'A1': obj['default'] = q_to_hex_twos(-a1, 30); return True
                        if tag == 'A2': obj['default'] = q_to_hex_twos(-a2, 31); return True
                        return False

                # CROSS OVER (A) and SUB CROSS OVER (B)
                if current_section == 'CROSS OVER BQs':
                    # Expect name like BQ1B0/B1/B2/A1/A2
                    if len(name) >= 4 and name.startswith('BQ'):
                        # crude parse: BQ<idx><coef>
                        # idx 1..5, coef in {B0,B1,B2,A1,A2}
                        try:
                            idx = int(name[2:-2])
                            tag = name[-2:]
                            if 1 <= idx <= len(sections_A) and tag in {'B0','B1','B2','A1','A2'}:
                                sos = sections_A[idx-1]
                                replaced = _set_coef(obj, tag, (sos.b0, sos.b1, sos.b2, sos.a1, sos.a2))
                        except Exception:
                            pass

                elif current_section == 'SUB CROSS OVER BQs':
                    if name.startswith('CH-SubBQ') and len(name) >= 10:
                        # CH-SubBQ<idx><tag>
                        try:
                            idx = int(name[8:-2])
                            tag = name[-2:]
                            if 1 <= idx <= len(sections_B) and tag in {'B0','B1','B2','A1','A2'}:
                                sos = sections_B[idx-1]
                                replaced = _set_coef(obj, tag, (sos.b0, sos.b1, sos.b2, sos.a1, sos.a2))
                        except Exception:
                            pass

                elif current_section == 'PHASE OPTIMIZER' and name.lower().startswith('delay'):
                    lname = name.lower()
                    # Spec: Channel A delay -> Delay Left and Delay Right; Channel B delay -> Delay Sub
                    if 'left' in lname or 'right' in lname:
                        obj['default'] = _hex_u32(delay_A)
                        replaced = True
                    elif 'sub' in lname:
                        obj['default'] = _hex_u32(delay_B)
                        replaced = True

                # EQ LEFT/RIGHT 14 BQs (14 sections) and INTGAIN (stage)
                elif current_section in ('EQ LEFT 14 BQs', 'EQ RIGHT 14 BQs') and eq_sections:
                    # Names like CH-LBQ1B0 / CH-RBQ1B0
                    if name.startswith('CH-LBQ') or name.startswith('CH-RBQ'):
                        try:
                            idx = int(name[6:-2])  # after CH-LBQ / CH-RBQ
                            tag = name[-2:]
                            if 1 <= idx <= len(eq_sections) and tag in {'B0','B1','B2','A1','A2'}:
                                vals = eq_sections[idx-1]
                                replaced = _set_coef(obj, tag, vals, stage=False)
                        except Exception:
                            pass

                elif current_section in ('LEFT INTGAIN BQ', 'RIGHT INTGAIN BQ') and eq_sections:
                    # Expect 5 rows (B0,B1,B2,A1,A2) for stage gain
                    tag = name[-2:] if len(name) >= 2 else ''
                    if tag in {'B0','B1','B2','A1','A2'}:
                        replaced = _set_coef(obj, tag, eq_stage, stage=True)

                # INPUT MIXER (LefttoLeft, RighttoLeft, LefttoRight, RighttoRight)
                elif current_section == 'INPUT MIXER' and mixer_hex:
                    if name in mixer_hex:
                        obj['default'] = mixer_hex[name]
                        replaced = True

                # OUTPUT CROSS BAR (apply per-channel gains)
                elif current_section == 'OUTPUT CROSS BAR':
                    if name == 'AnalogLeftfromLeft':
                        obj['default'] = q_to_hex_twos(gain_A_lin, 23)
                        replaced = True
                    elif name == 'AnalogRightfromSub':
                        obj['default'] = q_to_hex_twos(gain_B_lin, 23)
                        replaced = True

                # Write out (modified or not)
                fout.write(json.dumps(obj) + '\n')
    except Exception as e:
        QtWidgets.QMessageBox.critical(parent, 'Export', f'Failed to export: {e}')
        return None

    return out_path
