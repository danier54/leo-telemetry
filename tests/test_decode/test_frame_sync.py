import pytest

from leo_telemetry.decode.constants import AX25_FLAG_BITS
from leo_telemetry.decode.frame_sync import (
    bit_destuff,
    bits_to_bytes,
    extract_frames,
    find_frame_boundaries,
)


def _stuff(bits: str) -> str:
    stuffed = ""
    consecutive_ones = 0
    for bit in bits:
        stuffed += bit
        consecutive_ones = consecutive_ones + 1 if bit == "1" else 0
        if consecutive_ones == 5:
            stuffed += "0"
            consecutive_ones = 0
    return stuffed


def test_extract_frame_from_hdlc_bitstream():
    body = b"\xffhello"
    stuffed_bits = _stuff("".join(f"{byte:08b}"[::-1] for byte in body))
    stream = "111" + AX25_FLAG_BITS + stuffed_bits + AX25_FLAG_BITS + "000"

    assert find_frame_boundaries(stream) == [(11, 60)]
    assert bits_to_bytes(bit_destuff(stuffed_bits)) == body
    assert extract_frames(stream) == [body]


def test_extract_multiple_frames_with_shared_flag():
    first = _stuff("".join(f"{byte:08b}"[::-1] for byte in b"one"))
    second = _stuff("".join(f"{byte:08b}"[::-1] for byte in b"two"))

    stream = AX25_FLAG_BITS + first + AX25_FLAG_BITS + second + AX25_FLAG_BITS

    assert extract_frames(stream) == [b"one", b"two"]


@pytest.mark.parametrize("invalid", ["not bits", "01012", b"\x7e"])
def test_find_frame_boundaries_rejects_non_bitstream_input(invalid):
    with pytest.raises((UnicodeDecodeError, ValueError)):
        find_frame_boundaries(invalid)


def test_bit_destuff():
    cases = [
        # Basic destuffing
        ['111110', '11111'],           # single stuff bit removed
        ['11110', '11110'],            # no stuff bit, unchanged
        ['a', ValueError],             # invalid input

        # Multiple stuff bits
        ['1111101111100', '11111111110'],  # two stuff bits removed
        ['111110111110', '1111111111'],  # back-to-back groups

        # Stuff bit in middle of longer sequence
        ['0111110', '011111'],          # leading zero before five 1s
        ['1111100', '111110'],          # stuff bit then zero after

        # All zeros
        ['000000', '000000'],           # no stuff bits needed

        # Mixed
        ['101010101010101010101010', '101010101010101010101010'],  # no stuff

        # Edge cases
        ['', ValueError],              # empty string (if your impl raises)
        ['111111', ValueError],        # six 1s with no stuff bit (invalid?)

        # Single characters
        ['0', '0'],
        ['1', '1'],
    ]

    for case in cases:
        try:
            result = bit_destuff(case[0])
            if result != case[1]:
                print("Expected: ", case[1], "   Received: ", result)
                raise Exception(case)
        except ValueError:
            if case[1] == ValueError:
                continue
            else:
                raise Exception
