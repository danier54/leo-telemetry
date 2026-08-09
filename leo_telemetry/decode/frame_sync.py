"""AX.25 frame boundary detection and bit-destuffing."""

from __future__ import annotations
import logging

from leo_telemetry.decode.constants import AX25_FLAG_BITS

logger = logging.getLogger(__name__)


def bits_to_bytes(bits: str) -> bytes:
    """Pack HDLC octets, which AX.25 transmits least-significant bit first."""
    if len(bits) % 8:
        raise ValueError("frame bit count must be a multiple of eight")
    if any(bit not in "01" for bit in bits):
        raise ValueError("bitstream must contain only '0' and '1'")
    return bytes(
        int(bits[index:index + 8][::-1], 2)
        for index in range(0, len(bits), 8)
    )


def extract_frames(bits: str) -> list[bytes]:
    """Extract, destuff, and pack complete frames from a raw bitstream."""
    frames: list[bytes] = []
    for start, end in find_frame_boundaries(bits):
        try:
            frames.append(bits_to_bytes(bit_destuff(bits[start:end])))
        except ValueError:
            logger.debug("Skipping malformed frame: ", start, end)
    return frames


def find_frame_boundaries(raw: bytes | str) -> list[tuple[int, int]]:
    """
    Locate AX.25 flag patterns in an ASCII '0'/'1' bitstring and return
    (start_idx, end_idx) pairs for each frame

    Returns an empty list if no valid boundaries are found
    """
    bits = raw.decode("ascii") if isinstance(raw, bytes) else raw
    if any(bit not in "01" for bit in bits):
        raise ValueError("bitstream must contain only '0' and '1'")

    flags: list[int] = []
    start = 0
    while (index := bits.find(AX25_FLAG_BITS, start)) != -1:
        flags.append(index)
        start = index + len(AX25_FLAG_BITS)

    return [
        (left + len(AX25_FLAG_BITS), right)
        for left, right in zip(flags, flags[1:])
        if right > left + len(AX25_FLAG_BITS)
    ]


def bit_destuff(bits: str) -> str:
    """
    Remove stuffed zero bits inserted after five consecutive 1-bits

    Raises ValueError if the input is malformed
    """
    if not bits:
        raise ValueError

    if not all(b in "01" for b in bits):
        raise ValueError

    unstuffed = ""
    ones = 0
    for b in bits:
        if b == "1":
            ones += 1
        elif ones == 5:
            ones = 0
            continue
        else:
            ones = 0
        if ones > 5:
            raise ValueError
        unstuffed += b
    return unstuffed
