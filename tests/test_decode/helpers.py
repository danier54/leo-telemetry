"""Shared helpers for decode tests."""

from leo_telemetry.decode.crc16 import crc16_ccitt


def build_ax25_frame(
    *,
    addresses: list[bytes],
    control_pid: bytes,
    info: bytes,
    append_fcs: bool,
) -> bytes:
    """Assemble an AX.25 frame from already-shifted address fields."""
    body = b"".join(addresses) + control_pid + info
    if not append_fcs:
        return body
    fcs = crc16_ccitt(body)
    return body + fcs.to_bytes(2, byteorder="little")


def shifted_address(callsign: str, ssid: int, *, last: bool) -> bytes:
    """Encode a callsign and SSID as a seven-byte AX.25 address field."""
    padded = callsign.ljust(6)[:6]
    shifted = bytes((ord(character) << 1) for character in padded)
    ssid_byte = (ssid << 1) | 0x01 if last else (ssid << 1)
    return shifted + bytes([ssid_byte])


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
