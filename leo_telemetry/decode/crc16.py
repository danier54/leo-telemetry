"""CRC-16 Frame Check Sequence validation."""

from __future__ import annotations


def crc16_ccitt(data: bytes) -> int:
    """
    Compute the CRC-16/X.25 checksum used by AX.25 FCS fields

    Returns a 16-bit integer
    """
    raise NotImplementedError


def verify_fcs(frame: bytes) -> bool:
    """
    Validate a frame's trailing FCS bytes against a computed CRC-16

    Returns True if valid, False if too short or otherwise malformed
    """
    raise NotImplementedError
