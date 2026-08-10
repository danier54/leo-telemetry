"""AFSK1200 (Bell 202) audio demodulation: audio samples -> raw bitstream.

Prerequisite to frame_sync.find_frame_boundaries / bit_destuff when working
from real off-air recordings (see tests/fixtures/afsk1200_samples.py)
instead of SatNOGS's already-decoded telemetry bytes. Everything downstream
of demodulate() -- flag matching, bit-destuffing, CRC-16 -- is unchanged;
this just produces the same kind of stuffed bitstream frame_sync already
expects, one layer earlier than the byte-level golden frames provide it.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np

import soundfile as sf

from leo_telemetry.decode.frame_sync import AX25_FLAG_BITS

AFSK1200_BAUD_RATE = 1200
AFSK1200_MARK_FREQUENCY_HZ = 1200
AFSK1200_SPACE_FREQUENCY_HZ = 2200


def decode_audio(audio: bytes) -> tuple[np.ndarray, int]:
    """Decode the OGG recording into mono samples and its sample rate.

    Container decoding is separate from demodulation so the digital signal
    processing can be tested with generated pulse-code modulation (PCM)
    without creating temporary audio files
    """
    samples, sample_rate_hz = sf.read(BytesIO(audio), dtype="float64")
    return samples, int(sample_rate_hz)


def _nrzi_decode(tones: list[bool]) -> str:
    """Decode Bell 202 tone states: transition is zero, no transition is one"""
    return "".join(
        "1" if previous == current else "0"
        for previous, current in zip(tones, tones[1:])
    )


def demodulate(samples: np.ndarray, sample_rate_hz: int) -> str:
    """Demodulate mono PCM AFSK1200 samples into a raw bitstream.

    Output still has AX.25 flag bytes and bit-stuffing
    """
    # AFSK1200 transmits 1200 symbols per second. The number of PCM samples in
    # a symbol may be fractional, so symbol positions are rounded individually.
    samples_per_symbol = sample_rate_hz / AFSK1200_BAUD_RATE
    window_size = round(samples_per_symbol)

    # Build one reference wave for each Bell 202 tone.
    time = np.arange(window_size, dtype=np.float64) / sample_rate_hz
    mark_reference = np.exp(
        -2j * np.pi * AFSK1200_MARK_FREQUENCY_HZ * time
    )
    space_reference = np.exp(
        -2j * np.pi * AFSK1200_SPACE_FREQUENCY_HZ * time
    )

    best_bits = ""
    most_flags = -1

    # A recording can begin anywhere within a symbol. Try each possible sample
    # offset and keep the phase that produces the strongest AX.25 evidence.
    for phase in range(int(np.ceil(samples_per_symbol))):
        tones: list[bool] = []
        symbol_index = 0
        while True:
            start = int(round(phase + symbol_index * samples_per_symbol))
            chunk = samples[start:start + window_size]
            if len(chunk) < window_size:
                break

            # Remove any DC offset, compare the chunk with both reference
            # tones, and record which tone contains more energy.
            chunk = chunk - chunk.mean()
            mark_energy = abs(np.dot(chunk, mark_reference)) ** 2
            space_energy = abs(np.dot(chunk, space_reference)) ** 2
            tones.append(mark_energy >= space_energy)
            symbol_index += 1

        # Prefer the symbol timing that produces the most HDLC flags.
        bits = _nrzi_decode(tones)
        flag_count = bits.count(AX25_FLAG_BITS)
        if flag_count > most_flags:
            best_bits = bits
            most_flags = flag_count

    return best_bits
