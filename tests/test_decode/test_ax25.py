from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.crc16 import crc16_ccitt, verify_fcs
from tests.fixtures.golden_frames import load_golden_frames

# Real captured frames to decode against -- see tests/fixtures/golden_frames.py
GOLDEN_FRAMES = load_golden_frames()


@pytest.mark.skip(reason="TODO: implement once frame sync is built")
def test_decode_frame_strips_addressing_and_validates_crc():
    ...


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
