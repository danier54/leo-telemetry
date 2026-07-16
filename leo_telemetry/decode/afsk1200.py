"""AFSK1200 (Bell 202) audio demodulation: audio samples -> raw bitstream.

Prerequisite to frame_sync.find_frame_boundaries / bit_destuff when working
from real off-air recordings (see tests/fixtures/afsk1200_samples.py)
instead of SatNOGS's already-decoded telemetry bytes. Everything downstream
of demodulate() -- flag matching, bit-destuffing, CRC-16 -- is unchanged;
this just produces the same kind of stuffed bitstream frame_sync already
expects, one layer earlier than the byte-level golden frames provide it.
"""

from __future__ import annotations


def demodulate(audio: bytes, sample_rate_hz: int) -> str:
    """Demodulate mono PCM AFSK1200 audio into a raw '0'/'1' bitstream.

    Output still has AX.25 flag bytes and bit-stuffing intact -- hand it to
    frame_sync.find_frame_boundaries / bit_destuff next.
    """
    raise NotImplementedError
