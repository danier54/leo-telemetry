# Author: Taurean Newsome
# OSU Email: newsotau@oregonstate.edu
# Gitzhub username: newtau
# Description: Implements helper utilities and bunary parses for mission specifications.


from __future__ import annotations

import struct
from typing import Any


def unpack_from_view(format_str: struct.Struct, buffer: memoryview, offset: int) -> tuple[Any, ...]:
    """
    Unpack fields from a memory view using short-circuited guard clauses.

    Args:
        format_str: Pre-compiled C-level struct schema.
        buffer: The zero-copy memory view of the binary payload.
        offset: Starting byte offset in the buffer.

    Returns:
        A tuple of unpacked primitive Python values.

    Raises:
        ValueError: If buffer size is insufficient for the struct layout.
    """
    if len(buffer) < offset + format_str.size:
        raise ValueError(
            f"Buffer overflow: Struct requires {format_str.size} bytes at offset {offset}, "
            f"but buffer length is {len(buffer)}."
        )
    return format_str.unpack_from(buffer, offset)


def parse_ascii_hex(
    buffer: memoryview,
    start: int,
    length: int = 2,
    *,
    signed: bool = False,
    scale: float = 1.0,
) -> float:
    """
    Decode an ASCII-hex memory slice into scaled floating-point physical units.

    Args:
        buffer: The zero-copy memory view containing ASCII hex characters.
        start: Starting byte offset in the buffer.
        length: Number of ASCII bytes to read (default: 2).
        signed: If True, applies 8-bit two's complement conversion.
        scale: Multiplication factor for physical unit conversion (default: 1.0).

    Returns:
        The scaled floating-point physical measurement matching TelemetryMetric.value.

    Raises:
        ValueError: If the slice is out of bounds or invalid base-16 ASCII text.
    """
    if len(buffer) < start + length:
        raise ValueError(f"ASCII hex slice out of bounds at offset {start}.")

    try:
        raw_str = str(bytes(buffer[start : start + length]), encoding="ascii")
        val = int(raw_str, 16)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(
            f"Invalid ASCII-hex bytes at offset {start}: {buffer[start:start+length]!r}"
        ) from exc

    if signed and val >= 128:
        val -= 256

    return float(val * scale)
