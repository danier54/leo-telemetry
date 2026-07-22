"""AX.25 frame boundary detection and bit-destuffing."""

from __future__ import annotations


def find_frame_boundaries(raw: bytes) -> list[tuple[int, int]]:
    """
    Locate AX.25 flag bytes (0x7E) and return
    (start_idx, end_idx) pairs for each frame

    Returns an empty list if no valid boundaries are found
    """
    raise NotImplementedError


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
