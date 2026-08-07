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
    """Decode the OGG recording into normalized mono samples and its rate.

    Container decoding is separate from demodulation so the digital signal
    processing can be tested with generated pulse-code modulation (PCM)
    without creating temporary audio files
    """

    samples, sample_rate_hz = sf.read(BytesIO(audio), dtype="float64")

    # Normalize the recording to a consistent range without dividing silent
    # audio by zero. Tone comparison depends on relative, not absolute, power.
    peak = float(np.max(np.abs(samples), initial=0.0))
    if peak:
        samples = samples / peak
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
    # Use a consistent numeric representation before validating or processing
    # samples supplied by audio files and generated tests.
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim != 1:
        raise ValueError("samples must be one-dimensional mono PCM")

    # The sample rate must be high enough to represent the higher 2200 Hz
    # space tone without aliasing.
    if sample_rate_hz <= 2 * AFSK1200_SPACE_FREQUENCY_HZ:
        raise ValueError("sample rate must exceed the Nyquist rate\
                          for 2200 Hz")
    if not np.all(np.isfinite(samples)):
        raise ValueError("samples must contain only finite values")

    # AFSK1200 transmits 1200 symbols per second. The number of PCM samples in
    # a symbol may be fractional, so symbol positions are rounded individually.
    samples_per_symbol = sample_rate_hz / AFSK1200_BAUD_RATE
    window_size = max(4, int(round(samples_per_symbol)))
    if len(samples) < window_size * 2:
        return ""

    # Build one reference wave for each Bell 202 tone. The Hann window reduces
    # interference caused by cutting a continuous waveform at symbol edges.
    window = np.hanning(window_size)
    time = np.arange(window_size, dtype=np.float64) / sample_rate_hz
    mark_reference = window * np.exp(
        -2j * np.pi * AFSK1200_MARK_FREQUENCY_HZ * time
    )
    space_reference = window * np.exp(
        -2j * np.pi * AFSK1200_SPACE_FREQUENCY_HZ * time
    )

    best_bits = ""
    best_score = (-1, float("-inf"))

    # A recording can begin anywhere within a symbol. Try each possible sample
    # offset and keep the phase that produces the strongest AX.25 evidence.
    for phase in range(int(np.ceil(samples_per_symbol))):
        tones: list[bool] = []
        confidence = 0.0
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
            confidence += abs(mark_energy - space_energy) / (
                mark_energy + space_energy + np.finfo(float).eps
            )
            symbol_index += 1

        # Prefer candidates containing more HDLC flags. Average tone confidence
        # breaks ties without favoring longer recordings.
        bits = _nrzi_decode(tones)
        score = (bits.count(AX25_FLAG_BITS), confidence / max(1, len(tones)))
        if score > best_score:
            best_bits = bits
            best_score = score

    return best_bits


def demodulate_audio(audio: bytes) -> str:
    """Decode an audio container and demodulate it to raw bits."""
    samples, sample_rate_hz = decode_audio(audio)
    return demodulate(samples, sample_rate_hz)
