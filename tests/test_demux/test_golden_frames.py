"""Golden-frame integration tests for structural demultiplexing.

Validates that real-world SatNOGS payload captures loaded from the shared
fixture (`load_golden_frames`) are either correctly demultiplexed into
physical TelemetryReading models or rejected (returning None) when
captures contain RF noise or truncation.
"""

from __future__ import annotations

from typing import Any
import pytest

from leo_telemetry.common.models import DecodedFrame, RawFrame, TelemetryReading
from leo_telemetry.demux.demux import demultiplex
from tests.fixtures.golden_frames import load_golden_frames

# NORAD IDs
NORAD_ID_CAPE1 = 31130
NORAD_ID_ORESAT = 60525
NORAD_ID_CP16 = 68458

# Expectation Constants
EXPECTED_ORESAT_METRIC_COUNT = 6
EXPECTED_CP16_METRIC_COUNT = 6

# Hardware Thresholds
MIN_VALID_PAYLOAD_BYTES = 10
MAX_VBATT_MILLIVOLTS = 30000.0  # 30 V upper bound for CubeSat battery pack/bus voltage
MAX_VCELL_MILLIVOLTS = 30000.0   # 5 V upper bound for individual Li-Po cell voltage
MAX_STORAGE_PERCENT = 255.0     # Uncalibrated uint8 register ceiling (0-255)


def _to_decoded_frame(raw_frame: RawFrame) -> DecodedFrame:
    """Adapt an ingested RawFrame into a DecodedFrame for demux ingestion.

    Args:
        raw_frame: The raw telemetry model loaded from the golden dataset.

    Returns:
        A DecodedFrame populated with the raw payload bytes and valid CRC status.
    """
    return DecodedFrame(
        norad_id=raw_frame.norad_id,
        received_at=raw_frame.received_at,
        src_callsign="SATNOGS",
        dest_callsign="EARTH",
        payload=raw_frame.raw_bytes,
        crc_valid=True,
    )


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
        frame
        for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_ORESAT
        and len(frame.raw_bytes) >= MIN_VALID_PAYLOAD_BYTES
    ]

    assert len(valid_oresat_frames) >= 2, (
        f"Expected at least 2 valid ORESAT0.5 records; found {len(valid_oresat_frames)}."
    )

    for raw_frame in valid_oresat_frames:
        decoded_frame = _to_decoded_frame(raw_frame)
        reading = demultiplex(decoded_frame)

        assert reading is not None, (
            f"Failed to demultiplex valid ORESAT0.5 observation {raw_frame.observation_id}."
        )
        assert reading.norad_id == NORAD_ID_ORESAT
        assert len(reading.metrics) == EXPECTED_ORESAT_METRIC_COUNT

        metrics = _extract_metric_values(reading)
        # Verify physical voltage bounds
        assert 0.0 <= metrics["battery_1_pack_1_vbatt"] <= MAX_VBATT_MILLIVOLTS, (
            f"vbatt out of bounds for observation {raw_frame.observation_id}."
        )
        assert 0.0 <= metrics["battery_1_pack_1_vcell"] <= MAX_VCELL_MILLIVOLTS, (
            f"vcell out of bounds for observation {raw_frame.observation_id}."
        )
        # Verify storage percentage and non-negative operational counters
        assert 0.0 <= metrics["system_storage_percent"] <= MAX_STORAGE_PERCENT
        assert metrics["system_uptime"] >= 0.0
        assert metrics["system_power_cycles"] >= 0.0


def test_golden_frames_cp16_valid_telemetry() -> None:
    """Assert full SAL-E/CP16 captures unpack into expected physical metrics."""
    all_raw_frames = load_golden_frames()
    cp16_frames = [
        frame
        for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_CP16
    ]

    assert len(cp16_frames) == 3, (
        f"Expected 3 SAL-E/CP16 records; found {len(cp16_frames)}."
    )

    for raw_frame in cp16_frames:
        decoded_frame = _to_decoded_frame(raw_frame)
        reading = demultiplex(decoded_frame)

        assert reading is not None, (
            f"Failed to demultiplex SAL-E/CP16 observation {raw_frame.observation_id}."
        )
        assert reading.norad_id == NORAD_ID_CP16
        assert len(reading.metrics) == EXPECTED_CP16_METRIC_COUNT

        metrics = _extract_metric_values(reading)
        # Verify CPU time and packet/storage counters are non-negative
        assert metrics["user_cpu_time"] >= 0.0, (
            f"Negative CPU uptime in observation {raw_frame.observation_id}."
        )
        assert metrics["comms_rx_packets"] >= 0.0
        assert metrics["dir_data_free_value"] >= 0.0


def test_golden_frames_rejects_truncated_or_noise_captures() -> None:
    """Assert malformed captures and non-telemetry beacon snippets return None.

    Verifies that real-world RF noise or truncated frames do not raise unhandled
    exceptions and are filtered out by the demultiplexer.
    """
    all_raw_frames = load_golden_frames()

    # Validate rejection of a truncated 1-byte ORESAT0.5 capture (hex: "00")
    truncated_oresat_frame = next(
        frame
        for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_ORESAT
        and len(frame.raw_bytes) < MIN_VALID_PAYLOAD_BYTES
    )
    truncated_decoded = _to_decoded_frame(truncated_oresat_frame)
    assert demultiplex(truncated_decoded) is None, (
        "Expected None when demultiplexing a truncated ORESAT0.5 frame."
    )

    # Validate rejection of CAPE-1 ASCII beacon snippets lacking the 'K5USL' header
    cape1_noise_frames = [
        frame
        for frame in all_raw_frames
        if frame.norad_id == NORAD_ID_CAPE1
    ]
    assert len(cape1_noise_frames) == 3, (
        f"Expected 3 CAPE-1 noise records; found {len(cape1_noise_frames)}."
    )

    for raw_frame in cape1_noise_frames:
        noise_decoded = _to_decoded_frame(raw_frame)
        assert demultiplex(noise_decoded) is None, (
            f"Expected None for CAPE-1 non-telemetry beacon {raw_frame.observation_id}."
        )