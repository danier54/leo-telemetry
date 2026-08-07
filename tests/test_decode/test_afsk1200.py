from datetime import datetime

import numpy as np

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.afsk1200 import (
    AFSK1200_BAUD_RATE,
    AFSK1200_MARK_FREQUENCY_HZ,
    AFSK1200_SPACE_FREQUENCY_HZ,
    decode_audio,
    demodulate,
)
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.crc16 import verify_fcs
from leo_telemetry.decode.frame_sync import AX25_FLAG_BITS, extract_frames
from tests.fixtures.afsk1200_samples import load_afsk1200_sample


def _afsk_encode(bits: str, sample_rate_hz: int = 22050) -> np.ndarray:
    frequency = AFSK1200_MARK_FREQUENCY_HZ
    phase = 0.0
    samples: list[float] = []
    samples_per_symbol = sample_rate_hz / AFSK1200_BAUD_RATE

    for symbol_index, bit in enumerate(bits):
        if bit == "0":
            frequency = (
                AFSK1200_SPACE_FREQUENCY_HZ
                if frequency == AFSK1200_MARK_FREQUENCY_HZ
                else AFSK1200_MARK_FREQUENCY_HZ
            )
        start = round(symbol_index * samples_per_symbol)
        end = round((symbol_index + 1) * samples_per_symbol)
        for _ in range(end - start):
            samples.append(np.sin(phase))
            phase += 2 * np.pi * frequency / sample_rate_hz

    return np.asarray(samples)


def test_demodulate_recovers_nrzi_hdlc_flags():
    expected = AX25_FLAG_BITS * 6 + "0010110100101101" + AX25_FLAG_BITS * 6

    recovered = demodulate(_afsk_encode("1010" + expected + "1010"), 22050)

    assert expected in recovered


def test_real_iss_recording_recovers_valid_oracle_packet():
    sample = load_afsk1200_sample()
    pcm, sample_rate_hz = decode_audio(sample.audio_ogg)

    frames = [
        frame
        for frame in extract_frames(demodulate(pcm, sample_rate_hz))
        if verify_fcs(frame)
    ]
    decoded = [
        decode_frame(
            RawFrame(
                norad_id=sample.provenance["norad_id"],
                observation_id=sample.provenance["observation_id"],
                observer_station_id=0,
                received_at=datetime.fromisoformat(
                    sample.provenance["captured_at"].replace("Z", "+00:00")
                ),
                raw_bytes=frame,
            ),
            has_fcs=True,
        )
        for frame in frames
    ]

    expected = sample.packets[0]
    assert sample_rate_hz == sample.sample_rate_hint_hz
    assert any(
        frame is not None
        and frame.src_callsign == expected.source.removesuffix("-0")
        and frame.dest_callsign == expected.destination.removesuffix("-0")
        and frame.payload.decode("ascii") == expected.payload
        for frame in decoded
    )
