from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.crc16 import crc16_ccitt, verify_fcs
from leo_telemetry.decode.frame_sync import AX25_FLAG_BITS, extract_frames
from tests.fixtures.golden_frames import load_golden_frames

# Real captured frames to decode against -- see tests/fixtures/golden_frames.py
GOLDEN_FRAMES = load_golden_frames()


def test_decode_frame_strips_addressing_and_validates_crc():
    received_at = datetime(2026, 8, 8, tzinfo=timezone.utc)
    payload = b"frame sync integration"
    frame = _build_ax25_frame(
        addresses=[
            _shifted_address("CQ", 0, last=False),
            _shifted_address("KJ6ABC", 0, last=True),
        ],
        control_pid=b"\x03\xf0",
        info=payload,
        append_fcs=True,
    )
    frame_bits = "".join(f"{byte:08b}"[::-1] for byte in frame)
    stuffed_bits = _stuff_bits(frame_bits)

    extracted = extract_frames(
        AX25_FLAG_BITS + stuffed_bits + AX25_FLAG_BITS
    )

    assert extracted == [frame]
    decoded = decode_frame(
        RawFrame(
            norad_id=25544,
            observation_id=42,
            observer_station_id=7,
            received_at=received_at,
            raw_bytes=extracted[0],
        ),
        has_fcs=True,
    )

    assert decoded is not None
    assert decoded.norad_id == 25544
    assert decoded.received_at == received_at
    assert decoded.dest_callsign == "CQ"
    assert decoded.src_callsign == "KJ6ABC"
    assert decoded.payload == payload
    assert decoded.crc_valid is True


def test_verify_fcs_rejects_corrupted_frame():
    """
    Take a known-good frame, corrupt a byte in the payload, and assert
    that verify_fcs returns False.
    """
    # Build a minimal valid frame: 1 byte payload + correct FCS appended
    payload = b"\x82\x84\x86\x88\x8a\x8c\xe0"
    fcs = crc16_ccitt(payload)
    valid_frame = payload + fcs.to_bytes(2, byteorder="little")

    assert verify_fcs(valid_frame), "Sanity check: valid frame should pass FCS"

    # Corrupt a byte in the middle of the payload
    corrupted = bytearray(valid_frame)
    corrupted[3] ^= 0xFF
    assert not verify_fcs(bytes(corrupted)), (
        "Corrupted frame should fail FCS validation"
    )


def _build_ax25_frame(*, addresses: list[bytes], control_pid: bytes, info: bytes, append_fcs: bool) -> bytes:
    """Assemble a minimal AX.25 frame from already-shifted 7-byte address fields."""
    body = b"".join(addresses) + control_pid + info
    if not append_fcs:
        return body
    fcs = crc16_ccitt(body)
    return body + fcs.to_bytes(2, byteorder="little")


def _shifted_address(callsign: str, ssid: int, *, last: bool) -> bytes:
    padded = callsign.ljust(6)[:6]
    shifted = bytes((ord(c) << 1) for c in padded)
    ssid_byte = (ssid << 1) | 0x01 if last else (ssid << 1)
    return shifted + bytes([ssid_byte])


def _stuff_bits(bits: str) -> str:
    stuffed = ""
    consecutive_ones = 0
    for bit in bits:
        stuffed += bit
        consecutive_ones = consecutive_ones + 1 if bit == "1" else 0
        if consecutive_ones == 5:
            stuffed += "0"
            consecutive_ones = 0
    return stuffed


def test_decode_frame_validates_fcs_when_has_fcs_true():
    dest = _shifted_address("CQ", 0, last=False)
    src = _shifted_address("KJ6ABC", 0, last=True)
    frame_bytes = _build_ax25_frame(
        addresses=[dest, src], control_pid=b"\x03\xf0", info=b"hello", append_fcs=True
    )
    raw = RawFrame(
        norad_id=25544,
        observation_id=1,
        observer_station_id=1,
        received_at=datetime.now(timezone.utc),
        raw_bytes=frame_bytes,
    )

    result = decode_frame(raw, has_fcs=True)

    assert result is not None
    assert result.crc_valid is True
    assert result.payload == b"hello"

    corrupted = bytearray(frame_bytes)
    corrupted[-3] ^= 0xFF
    assert decode_frame(
        RawFrame(norad_id=25544, observation_id=2, observer_station_id=1,
                  received_at=datetime.now(timezone.utc), raw_bytes=bytes(corrupted)),
        has_fcs=True,
    ) is None


def test_decode_frame():
    for frame in GOLDEN_FRAMES:
        result = decode_frame(frame)

        if len(frame.raw_bytes) < 15:
            assert result is None, f"observation {frame.observation_id}: "\
                "expected None for short frame, got {result}"
            continue

        assert result is not None, (
            f"observation {frame.observation_id}: "
            f"expected DecodedFrame, got None"
        )
        assert result.norad_id == frame.norad_id, (
            f"observation {frame.observation_id}: norad_id mismatch"
        )
        assert result.received_at == frame.received_at, (
            f"observation {frame.observation_id}: received_at mismatch"
        )
        assert isinstance(result.src_callsign, str), (
            f"observation {frame.observation_id}: src_callsign is not a str"
        )
        assert isinstance(result.dest_callsign, str), (
            f"observation {frame.observation_id}: dest_callsign is not a str"
        )
