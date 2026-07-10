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
