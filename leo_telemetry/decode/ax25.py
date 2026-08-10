"""AX.25 address stripping and top-level frame decoding."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, RawFrame
from leo_telemetry.decode.constants import (
    AX25_ADDRESS_BYTE_SHIFT,
    AX25_ADDRESS_BYTES,
    AX25_ADDRESS_EXTENSION_BIT,
    AX25_CALLSIGN_BYTES,
    AX25_CONTROL_AND_PID_BYTES,
    AX25_FCS_BYTES,
    AX25_MIN_ADDRESS_FIELDS,
    CW_NORAD_IDS,
    MIN_FRAME_BYTES,
)
from leo_telemetry.decode.crc16 import verify_fcs
from leo_telemetry.decode.cw import decode_cw_beacon


def decode_address(address_bytes: bytes | memoryview) -> str:
    """
    Decodes field for AX.25 by shifting each byte right by 1 for
    first 6 bytes

    Returns ASCII string from shifted bytes
    """
    callsign = bytes(
        byte >> AX25_ADDRESS_BYTE_SHIFT
        for byte in address_bytes[:AX25_CALLSIGN_BYTES]
    )
    return callsign.decode("ascii").strip()


def decode_frame(raw: RawFrame, *, has_fcs: bool = False) -> \
        DecodedFrame | None:
    """
    Run address parsing (and, for frames that carry one, FCS validation)
    on a raw frame.

    `has_fcs` distinguishes two kinds of RawFrame:
        - SatNOGS DB telemetry (the default, has_fcs=False): the API
          already strips and validates the FCS server-side, so raw_bytes
          has no trailer left to check. crc_valid=True by provenance.
        - Audio-demodulated frames (has_fcs=True): raw_bytes still has
          its trailing FCS, which we validate ourselves.

    Pipeline:
        1. Reject obviously invalid input (null, too short)
        2. If has_fcs, validate FCS via crc16.verify_fcs() and bail on failure
        3. Parse header fields and info payload
        4. Return DecodedFrame, or None if any step fails

    Returns None if the frame is malformed or fails FCS validation.
    """
    if raw is None:
        return None

    # CW satellites (CAPE-1) downlink Morse transcriptions, not AX.25
    # framing; route them to the CW beacon decoder, which validates the
    # documented beacon structure and drops noise.
    if raw.norad_id in CW_NORAD_IDS:
        return decode_cw_beacon(raw)

    if len(raw.raw_bytes) < MIN_FRAME_BYTES:
        return None

    if has_fcs and not verify_fcs(raw.raw_bytes):
        return None

    # Parse addresses
    buffer = memoryview(raw.raw_bytes)
    addresses: list[str] = []
    i = 0
    found_last_address = False

    while i + AX25_ADDRESS_BYTES <= len(buffer):
        chunk = buffer[i:i + AX25_ADDRESS_BYTES]
        addresses.append(decode_address(chunk))
        i += AX25_ADDRESS_BYTES
        if chunk[-1] & AX25_ADDRESS_EXTENSION_BIT:
            found_last_address = True
            break               # stop -- reached end of the address list
        # extension bit clear: more address fields follow, keep reading them

    # Running out of buffer without ever seeing the extension bit means the
    # "addresses" we collected aren't real AX.25 addresses at all -- reject
    # rather than build a frame out of whatever we happened to slice off.
    if not found_last_address or len(addresses) < AX25_MIN_ADDRESS_FIELDS:
        return None

    dest_callsign = addresses[0]
    src_callsign = addresses[1]
    payload_start = i + AX25_CONTROL_AND_PID_BYTES
    if has_fcs:
        payload = raw.raw_bytes[payload_start:-AX25_FCS_BYTES]
    else:
        payload = raw.raw_bytes[payload_start:]

    return DecodedFrame(
        norad_id=raw.norad_id,
        received_at=raw.received_at,
        src_callsign=src_callsign,
        dest_callsign=dest_callsign,
        payload=payload,
        crc_valid=crc_valid,
    )