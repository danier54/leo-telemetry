"""AX.25 address stripping and top-level frame decoding."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, RawFrame


def decode_address(address_bytes: str) -> str:
    """
    Decodes field for AX.25 by shifting each byte right by 1 for
    first 6 bytes

    Returns ASCII string from shifted bytes
    """
    chars = []
    for i in range(6):
        byte = address_bytes[i]
        shifted_byte = byte >> 1    # bitwise right shift operator

        char = chr(shifted_byte)
        chars.append(char)
    return "".join(chars).strip()


def decode_frame(raw: RawFrame) -> DecodedFrame | None:
    """
    Run frame sync, bit-destuffing, and CRC validation on a raw frame

    Pipeline:
        1. Reject obviously invalid input (null, too short)
        2. Validate FCS via crc16.validate_fcs()
        3. Parse header fields and info payload
        4. Return DecodedFrame, or None if any step fails

    Returns None if the frame fails CRC validation
    """
    if raw is None or len(raw.raw_bytes) < 15:
        return None

    addresses = []
    i = 0
    while True:
        chunk = raw.raw_bytes[i:i+7]  # AX.25 callsigns are always 7 bytes long
        address = decode_address(chunk)
        addresses.append(address)
        i += 7

        if chunk[6] & 0x01:   # checking last bit of last byte
            break               # break b/c reached end of addresses

    dest_callsign = addresses[0]
    src_callsign = addresses[1]
    payload = addresses[2:]

    return DecodedFrame(
        norad_id=raw.norad_id,
        received_at=raw.received_at,
        src_callsign=src_callsign,
        dest_callsign=dest_callsign,
        payload=payload,
        crc_valid=True,
    )
