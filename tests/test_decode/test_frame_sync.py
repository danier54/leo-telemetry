from leo_telemetry.decode.frame_sync import bit_destuff


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
