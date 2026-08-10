"""CRC-16 Frame Check Sequence validation."""

from __future__ import annotations

from crccheck.crc import Crc16X25

from leo_telemetry.decode.constants import AX25_FCS_BYTES, MIN_FCS_FRAME_BYTES


def crc16_ccitt(data: bytes) -> int:
    """
    Compute the CRC-16/X.25 checksum used by AX.25 FCS fields with
    crccheck library

    Returns a 16-bit integer
    """
    return Crc16X25.calc(data)


def verify_fcs(frame: bytes) -> bool:
    """
    Validate a frame's trailing FCS bytes against a computed CRC-16

    Returns True if valid, False if too short or otherwise malformed
    """
    if len(frame) < MIN_FCS_FRAME_BYTES:
        return False

    payload = frame[:-AX25_FCS_BYTES]
    received_fcs = int.from_bytes(
        frame[-AX25_FCS_BYTES:], byteorder="little"
    )
    computed_fcs = crc16_ccitt(payload)

    return computed_fcs == received_fcs
