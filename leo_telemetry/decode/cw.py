"""CW (Morse) beacon decoding for satellites that do not transmit AX.25.

CAPE-1 transmits its telemetry as a CW beacon: the "K5USL" callsign
followed by a packet-type digit and ASCII-hex fields (the same layout
demux/specs/cape1_31130.py parses). SatNOGS CW decoders emit that as
character transcriptions, typically space-separated and frequently pure
noise when the signal is weak.

This module normalizes a transcription and validates it against the
documented beacon structure. Frames that do not contain the structure
are dropped as noise -- never forwarded with fabricated validity.
"""

from __future__ import annotations

import logging

from leo_telemetry.common.models import DecodedFrame, RawFrame
from leo_telemetry.decode.constants import (
    CW_CALLSIGN,
    CW_DEST_CALLSIGN,
    CW_HEX_DIGITS,
    CW_MIN_BEACON_CHARS,
    CW_MIN_HEX_CHARS,
    CW_NORAD_IDS as CW_NORAD_IDS,
    CW_PACKET_TYPES,
)

logger = logging.getLogger(__name__)


def decode_cw_beacon(raw: RawFrame) -> DecodedFrame | None:
    """Normalize a CW transcription and validate the CAPE-1 beacon layout.

    Returns:
        A DecodedFrame whose payload is the normalized beacon text
        ("K5USL" + type digit + hex fields) ready for the demux spec, or
        None when the transcription does not contain the documented
        structure. CW carries no frame checksum, so crc_valid=True here
        records that this structural validation passed, which is the
        strongest integrity check the modulation allows.
    """
    try:
        text = raw.raw_bytes.decode("ascii")
    except UnicodeDecodeError:
        return None

    # CW decoders separate characters with whitespace; collapse it away.
    normalized = "".join(text.upper().split())

    marker = normalized.find(CW_CALLSIGN)
    if marker < 0:
        return None

    beacon = normalized[marker:]
    if len(beacon) < CW_MIN_BEACON_CHARS:
        return None

    packet_type = beacon[len(CW_CALLSIGN)]
    if packet_type not in CW_PACKET_TYPES:
        return None

    # Keep the maximal run of hex characters after the type digit; a CW
    # decoder often trails off into noise mid-beacon.
    fields = beacon[len(CW_CALLSIGN) + 1 :]
    hex_run = 0
    while hex_run < len(fields) and fields[hex_run] in CW_HEX_DIGITS:
        hex_run += 1
    if hex_run < CW_MIN_HEX_CHARS:
        return None

    payload = f"{CW_CALLSIGN}{packet_type}{fields[:hex_run]}".encode("ascii")
    logger.debug(
        "CW beacon accepted for norad=%s: %d hex chars", raw.norad_id, hex_run
    )
    return DecodedFrame(
        norad_id=raw.norad_id,
        received_at=raw.received_at,
        src_callsign=CW_CALLSIGN,
        dest_callsign=CW_DEST_CALLSIGN,
        payload=payload,
        crc_valid=True,
    )
