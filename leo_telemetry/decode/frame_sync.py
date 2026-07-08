"""AX.25 frame boundary detection and bit-destuffing."""

from __future__ import annotations


def find_frame_boundaries(raw: bytes) -> list[tuple[int, int]]:
    """Locate AX.25 flag bytes (0x7E) marking frame start/end offsets."""
    raise NotImplementedError


def bit_destuff(bits: str) -> str:
    """Remove stuffed zero bits inserted after five consecutive 1-bits."""
    raise NotImplementedError
