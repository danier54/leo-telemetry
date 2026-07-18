from leo_telemetry.decode.ax25 import decode_frame
import pytest

from tests.fixtures.golden_frames import load_golden_frames

# Real captured frames to decode against -- see tests/fixtures/golden_frames.py
GOLDEN_FRAMES = load_golden_frames()


@pytest.mark.skip(reason="TODO: implement once frame sync/bit-destuffing is built")
def test_decode_frame_strips_addressing_and_validates_crc():
    ...


@pytest.mark.skip(reason="TODO: implement once CRC-16 module is built")
def test_verify_fcs_rejects_corrupted_frame():
    ...


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
        assert isinstance(result.crc_valid, bool), (
            f"observation {frame.observation_id}: crc_valid is not a bool"
        )
