"""Golden-frame integration tests for structural demultiplexing.

Validates that real-world SatNOGS payload captures loaded from the shared
fixture (`load_golden_frames`) are either correctly demultiplexed into
physical TelemetryReading models or rejected (returning None) when
captures contain RF noise or truncation.
"""

from __future__ import annotations

import pytest

from leo_telemetry.common.models import DecodedFrame, RawFrame, TelemetryReading
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.decode.ax25 import MIN_FRAME_BYTES, decode_frame
from tests.fixtures.golden_frames import load_golden_frames

# NORAD IDs
NORAD_ID_CAPE1 = 31130
NORAD_ID_ORESAT = 60525
NORAD_ID_CP16 = 68458

# Expectation Constants
EXPECTED_ORESAT_METRIC_COUNT = 6
EXPECTED_CP16_METRIC_COUNT = 6
EXPECTED_CAPE1_METRIC_COUNT = 8
# Matches decode_frame()'s own minimum so a "valid" frame here can never be
# too short for decode_frame() to actually decode.
MIN_VALID_PAYLOAD_BYTES = MIN_FRAME_BYTES

# Kaitai Struct Data Type Ceilings
MAX_U32 = 4294967295.0
MAX_CP16_DATA_FREE = 2147483647.0  # Top bit masked out
MAX_U16 = 65535.0
MAX_U8 = 255.0
MAX_S8 = 127.0
MIN_S8 = -128.0

# Hardware thresholds
MAX_VBATT_MILLIVOLTS = 30000.0  # 30 V upper bound for CubeSat battery pack
MAX_VCELL_MILLIVOLTS = 30000.0  # 5 V expected, 30V limit


def _extract_metric_values(reading: TelemetryReading) -> dict[str, float]:
    """Map a TelemetryReading's metrics into a name-to-value dictionary.

    Args:
        reading: The demultiplexed telemetry model.

    Returns:
        A dictionary mapping telemetry metric names to their numeric values.
    """
    return {metric.name: metric.value for metric in reading.metrics}


def test_golden_frames_oresat_valid_telemetry() -> None:
    """Assert full ORESAT0.5 captures unpack into expected physical metrics."""
    all_raw_frames = load_golden_frames()
    valid_oresat_frames = [
        frame for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_ORESAT and len(frame.raw_bytes) >= MIN_VALID_PAYLOAD_BYTES
    ]
    assert valid_oresat_frames, "no ORESAT0.5 golden frames to test against"

    checked = 0
    for raw_frame in valid_oresat_frames:
        decoded_frame = decode_frame(raw_frame)
        if not decoded_frame:
            continue
        checked += 1

        reading = demultiplex(decoded_frame)

        assert reading is not None
        assert len(reading.metrics) == EXPECTED_ORESAT_METRIC_COUNT

        metrics = _extract_metric_values(reading)

        # ORESAT Bounds
        assert 0.0 <= metrics["battery_1_pack_1_vbatt"] <= MAX_VBATT_MILLIVOLTS
        assert 0.0 <= metrics["battery_1_pack_1_vcell"] <= MAX_VCELL_MILLIVOLTS
        assert 0.0 <= metrics["system_storage_percent"] <= MAX_U8
        assert 0.0 <= metrics["system_uptime"] <= MAX_U32
        assert 0.0 <= metrics["system_power_cycles"] <= MAX_U16

    # A silent "continue" above must not let this test pass without checking anything.
    assert checked == len(valid_oresat_frames), (
        f"decode_frame() dropped {len(valid_oresat_frames) - checked} of "
        f"{len(valid_oresat_frames)} golden ORESAT0.5 frames -- the checks "
        "above ran zero times for those"
    )


def test_golden_frames_cp16_valid_telemetry() -> None:
    """Assert full SAL-E/CP16 captures unpack into expected physical metrics."""
    all_raw_frames = load_golden_frames()
    cp16_frames = [frame for frame in all_raw_frames if frame.norad_id == NORAD_ID_CP16]
    assert cp16_frames, "no SAL-E/CP16 golden frames to test against"

    checked = 0
    for raw_frame in cp16_frames:
        decoded_frame = decode_frame(raw_frame)

        if not decoded_frame:
            continue
        checked += 1

        reading = demultiplex(decoded_frame)

        assert reading is not None
        assert len(reading.metrics) == EXPECTED_CP16_METRIC_COUNT

        metrics = _extract_metric_values(reading)

        # CP16 / SAL-E Bounds
        assert 0.0 <= metrics["user_cpu_time"] <= MAX_U32
        assert 0.0 <= metrics["comms_rx_packets"] <= MAX_U32
        assert 0.0 <= metrics["dir_data_free_value"] <= MAX_CP16_DATA_FREE

        assert 0.0 <= metrics["daughter_a_temp_raw"] <= MAX_U8
        assert 0.0 <= metrics["payload_3v3_temp_raw"] <= MAX_U8
        assert 0.0 <= metrics["bus_3v3_volt_raw"] <= MAX_U8

    # A silent "continue" above must not let this test pass without checking anything.
    assert checked == len(cp16_frames), (
        f"decode_frame() dropped {len(cp16_frames) - checked} of "
        f"{len(cp16_frames)} golden SAL-E/CP16 frames -- the checks above "
        "ran zero times for those"
    )


def test_golden_frames_cape1_valid_telemetry() -> None:
    """Assert full CAPE-1 captures unpack into expected physical metrics."""
    all_raw_frames = load_golden_frames()
    
    # Filter for valid CAPE-1 frames containing the 'K5USL' magic header
    cape1_frames = [
        frame for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_CAPE1 and b'K5USL' in frame.raw_bytes
    ]
    if not cape1_frames:
        # All three captured CAPE-1 frames in golden_frames.json are noise/beacon
        # fragments (see test_golden_frames_rejects_truncated_or_noise_captures),
        # not real telemetry. Skip loudly instead of passing an empty loop, so
        # this stays visible as a gap until a real CAPE-1 capture is added.
        pytest.skip("golden_frames.json has no CAPE-1 frame with the 'K5USL' header")

    checked = 0
    for raw_frame in cape1_frames:
        decoded_frame = decode_frame(raw_frame)
        if not decoded_frame:
            continue
        checked += 1

        reading = demultiplex(decoded_frame)

        assert reading is not None
        assert len(reading.metrics) == EXPECTED_CAPE1_METRIC_COUNT

        metrics = _extract_metric_values(reading)

        # CAPE-1 Bounds (based on 2-byte ASCII hex decoding)
        for name, value in metrics.items():
            if "temp" in name:
                # Temperatures are two's complement signed 8-bit (-128 to 127)
                assert MIN_S8 <= value <= MAX_S8
            else:
                # Voltages, currents, and solar values are unsigned 8-bit (0 to 255)
                assert 0.0 <= value <= MAX_U8

    assert checked == len(cape1_frames), (
        f"decode_frame() dropped {len(cape1_frames) - checked} of "
        f"{len(cape1_frames)} golden CAPE-1 frames -- the checks above "
        "ran zero times for those"
    )


def test_golden_frames_rejects_truncated_or_noise_captures() -> None:
    """Assert malformed captures and non-telemetry beacon snippets return None.

    Verifies that real-world RF noise or truncated frames do not raise unhandled
    exceptions and are filtered out by the demultiplexer.
    """
    all_raw_frames = load_golden_frames()

    # Check ORESAT truncation
    truncated_oresat_frame = next(
        frame for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_ORESAT and len(frame.raw_bytes) < MIN_VALID_PAYLOAD_BYTES
    )
    
    # Verify demux handles bad inputs
    truncated_decoded = DecodedFrame(
        norad_id=NORAD_ID_ORESAT, received_at=truncated_oresat_frame.received_at,
        src_callsign="TEST", dest_callsign="EARTH", payload=truncated_oresat_frame.raw_bytes, crc_valid=True
    )
    assert demultiplex(truncated_decoded) is None

    # Validate rejection of CAPE-1 ASCII beacon snippets lacking the 'K5USL' header
    cape1_noise_frames = [frame for frame in all_raw_frames if frame.norad_id == NORAD_ID_CAPE1]
    
    for raw_frame in cape1_noise_frames:
        noise_decoded = DecodedFrame(
            norad_id=NORAD_ID_CAPE1, received_at=raw_frame.received_at,
            src_callsign="TEST", dest_callsign="EARTH", payload=raw_frame.raw_bytes, crc_valid=True
        )
        assert demultiplex(noise_decoded) is None
