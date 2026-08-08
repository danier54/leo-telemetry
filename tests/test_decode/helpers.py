"""Shared helpers for decode tests."""


def stuff_bits(bits: str) -> str:
    """Insert an HDLC zero after each run of five one-bits."""
    stuffed = ""
    consecutive_ones = 0
    for bit in bits:
        stuffed += bit
        consecutive_ones = consecutive_ones + 1 if bit == "1" else 0
        if consecutive_ones == 5:
            stuffed += "0"
            consecutive_ones = 0
    return stuffed
