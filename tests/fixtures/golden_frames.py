"""Loader for `golden_frames.json`: real frames captured from SatNOGS.

Intended for the decode track's tests (frame sync, bit-destuffing,
CRC-16) so development doesn't depend on guessing at frame structure
from scratch, and doesn't require access to the live ingest pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from leo_telemetry.common.models import RawFrame

GOLDEN_FRAMES_PATH = Path(__file__).parent / "golden_frames.json"


def load_golden_frames() -> list[RawFrame]:
    """Load the committed sample of real SatNOGS telemetry frames.

    Covers all three target satellites with a mix of frame lengths,
    including short/truncated-looking captures (useful for exercising
    CRC rejection) alongside full-length ones. CAPE-1 (31130) frames in
    this set are plain ASCII beacon text rather than binary AX.25 --
    worth knowing before assuming every frame needs bit-destuffing.
    """
    with GOLDEN_FRAMES_PATH.open() as fh:
        records = json.load(fh)

    return [
        RawFrame(
            norad_id=record["norad_id"],
            observation_id=record["observation_id"],
            observer_station_id=record["observer_station_id"],
            received_at=datetime.fromisoformat(record["received_at"]),
            raw_bytes=bytes.fromhex(record["raw_bytes_hex"]),
        )
        for record in records
    ]
