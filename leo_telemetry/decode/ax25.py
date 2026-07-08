"""AX.25 address stripping and top-level frame decoding."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, RawFrame


def decode_frame(raw: RawFrame) -> DecodedFrame | None:
    """Run frame sync, bit-destuffing, and CRC validation on a raw frame.

    Returns None if the frame fails CRC validation.
    """
    raise NotImplementedError
