import pytest


@pytest.mark.skip(reason="TODO(Jordan): implement once frame sync/bit-destuffing is built")
def test_decode_frame_strips_addressing_and_validates_crc():
    ...


@pytest.mark.skip(reason="TODO(Jordan): implement once CRC-16 module is built")
def test_verify_fcs_rejects_corrupted_frame():
    ...
