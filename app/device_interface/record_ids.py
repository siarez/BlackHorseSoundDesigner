from __future__ import annotations

"""
Central registry for journal record IDs used with type 0x52 (coeff bytes).

Keep this file authoritative to avoid collisions between features. Firmware
replays the latest (type,id) pairs on boot; reusing an ID for a different
feature would cause the older payload to be superseded in the journal index
and on boot apply.

Usage:
  from app.device_interface.record_ids import REC_EQ_L, TYPE_COEFF
  link.jwrb_with_log(TYPE_COEFF, REC_EQ_L, payload)
"""

# Journal type for 32-bit coefficient streams (book 0x8C):
TYPE_COEFF: int = 0x52
TYPE_APP_STATE: int = 0x53

# Reserved IDs (unique per feature/section)

# Crossover
REC_XO_A: int = 0x05           # CROSS OVER BQs (Channel A)
REC_XO_B: int = 0x06           # SUB CROSS OVER BQs (Channel B)
REC_PHASE: int = 0x07          # PHASE OPTIMIZER (Delays)
REC_OUT_GAINS: int = 0x08      # OUTPUT CROSS BAR (Gains)

# EQ
REC_EQ_L: int = 0x09           # EQ LEFT 14 BQs
REC_INTGAIN_L: int = 0x0A      # LEFT INTGAIN BQ
REC_EQ_R: int = 0x0B           # EQ RIGHT 14 BQs
REC_INTGAIN_R: int = 0x0C      # RIGHT INTGAIN BQ

# Input Mixer
REC_INPUT_MIXER: int = 0x10    # INPUT MIXER (LefttoLeft/RighttoLeft/LefttoRight/RighttoRight)

# Future expansion: 0x11..0x1F reserved
REC_MIX_GAIN: int = 0x11       # MIX/GAIN ADJUST (LefttoSub/RighttoSub/SubMixScratch*/BassMono*)

# UI App State sidecar (type 0x53). Inert at boot; used for Load From Device.
REC_STATE_EQ: int = 0x90
REC_STATE_XO: int = 0x91
REC_STATE_MIXER: int = 0x92
REC_STATE_MIXGAIN: int = 0x93
REC_STATE_XBAR: int = 0x94
