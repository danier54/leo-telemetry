"""Loader for `afsk1200_iss_aprs.ogg`: a real off-air AFSK1200 recording.

Unlike golden_frames.json (SatNOGS-decoded bytes -- frame sync, bit-destuffing,
and FCS already stripped by the ground station), this is the actual recorded
audio. Nothing has touched it yet, so it's meant for testing the
frame_sync/bit_destuff/crc16 modules against real RF instead of only
synthetic bitstreams.

Captured off the ISS APRS digipeater (145.825 MHz, AFSK1200) via SatNOGS
Network -- see the "provenance" key in afsk1200_iss_aprs_oracle.json for the
source observation. The "packets" list there was decoded independently with
multimon-ng (not our own code) and is ground truth to check a from-scratch
decoder against, the same role golden_frames.py's real captures play one
layer up.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

AUDIO_PATH = Path(__file__).parent / "afsk1200_iss_aprs.ogg"
ORACLE_PATH = Path(__file__).parent / "afsk1200_iss_aprs_oracle.json"


@dataclass(frozen=True)
class OraclePacket:
    """One AX.25 UI frame as decoded by the reference tool (multimon-ng)."""

    source: str
    destination: str
    path: str
    payload: str


@dataclass(frozen=True)
class Afsk1200Sample:
    """A real AFSK1200 recording plus its independently-decoded packets."""

    audio_ogg: bytes
    sample_rate_hint_hz: int
    packets: list[OraclePacket]
    provenance: dict


def load_afsk1200_sample() -> Afsk1200Sample:
    """Load the ISS APRS AFSK1200 recording and its oracle-decoded packets."""
    with ORACLE_PATH.open() as fh:
        oracle = json.load(fh)

    return Afsk1200Sample(
        audio_ogg=AUDIO_PATH.read_bytes(),
        sample_rate_hint_hz=oracle["sample_rate_hint_hz"],
        packets=[OraclePacket(**p) for p in oracle["packets"]],
        provenance=oracle["provenance"],
    )
