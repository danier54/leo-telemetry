"""AX.25 address stripping and top-level frame decoding."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, RawFrame


def decode_frame(raw: RawFrame) -> DecodedFrame | None:
    """
    Run frame sync, bit-destuffing, and CRC validation on a raw frame

    Pipeline:
        1. Reject obviously invalid input (null, too short)
        2. Find frame boundaries via frame_sync.find_frame_boundaries()
        3. Destuff bits via frame_sync.destuff_bits()
        4. Validate FCS via crc16.validate_fcs()
        5. Parse header fields and info payload
        6. Return DecodedFrame, or None if any step fails

    Returns None if the frame fails CRC validation
    """
    raise NotImplementedError
