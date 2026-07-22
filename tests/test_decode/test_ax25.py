from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.crc16 import crc16_ccitt, verify_fcs
import pytest

from tests.fixtures.golden_frames import load_golden_frames

# Real captured frames to decode against -- see tests/fixtures/golden_frames.py
GOLDEN_FRAMES = load_golden_frames()


@pytest.mark.skip(reason="TODO: implement once frame sync is built")
def test_decode_frame_strips_addressing_and_validates_crc():
    ...


@pytest.mark.skip(reason="TODO: implement once fcs validation decision made")
def test_verify_fcs_rejects_corrupted_frame():
    """
    Take a known-good frame, corrupt a byte in the payload, and assert
    that verify_fcs returns False.
    """
    # # Build a minimal valid frame: 1 byte payload + correct FCS appended
    # payload = b"\x82\x84\x86\x88\x8a\x8c\xe0"
    # fcs = crc16_ccitt(payload)
    # valid_frame = payload + fcs.to_bytes(2, byteorder="little")

    # assert verify_fcs(valid_frame), "Sanity check: valid frame should pass FCS"

    # # Corrupt a byte in the middle of the payload
    # corrupted = bytearray(valid_frame)
    # corrupted[3] ^= 0xFF
    # assert not verify_fcs(bytes(corrupted)), (
    #     "Corrupted frame should fail FCS validation"
    # )


def test_decode_frame():
    for frame in GOLDEN_FRAMES:
        result = decode_frame(frame)

        if len(frame.raw_bytes) < 15:
            assert result is None, f"observation {frame.observation_id}: "\
                "expected None for short frame, got {result}"
            continue

        # TODO: re-enable once FCS validation is implemented
        # if not verify_fcs(frame.raw_bytes):
        #     assert result is None, (...)
        #     continue

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
