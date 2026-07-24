"""Golden-frame automated unit test suite for LEO satellite demultiplexing.

Verifies byte-offset to physical-unit translation against known maintainer
specifications for ORESAT0.5 (60525), SAL-E/CP16 (68458), and CAPE-1 (31130).
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from leo_telemetry.common.models import DecodedFrame, TelemetryReading
from leo_telemetry.demux import demultiplex


def metrics_to_dict(reading: TelemetryReading) -> dict[str, float]:
    """Convert a tuple of TelemetryMetric objects into a key-value dictionary for clean assertions."""
    return {metric.name: metric.value for metric in reading.metrics}


@pytest.fixture
def oresat_golden_frame() -> DecodedFrame:
    """Generate a valid little-endian golden frame for ORESAT0.5 (NORAD ID: 60525)."""
    payload = bytearray(216)
    
    # Inject system uptime: 3600s (0x00000e10 little-endian) at offset 7
    payload[7:11] = b"\x10\x0e\x00\x00"
    # Inject system unix time: 1700000000s (0x65540300 little-endian) at offset 11
    payload[11:15] = b"\x00\xf1\x53\x65"
    # Inject system power cycles: 15 (0x000f little-endian) at offset 15
    payload[15:17] = b"\x0f\x00"
    # Inject system storage percent: 45% (0x2d) at offset 17
    payload[17:18] = b"\x2d"
    # Inject battery 1 pack 1 vbatt: 8200 mV (0x2008 little-endian) at offset 49
    payload[49:51] = b"\x08\x20"
    # Inject battery 1 pack 1 vcell: 4100 mV (0x1004 little-endian) at offset 51
    payload[51:53] = b"\x04\x10"

    return DecodedFrame(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=bytes(payload),
        crc_valid=True,
    )


@pytest.fixture
def cp16_golden_frame() -> DecodedFrame:
    """
    Generate a valid big-endian golden frame for SAL-E / CP16 (NORAD ID: 68458).

    Includes a 29-byte IPv4/UDP header and simulates the communications packet bug.
    """
    payload = bytearray(90)
    
    # Bytes 0..28 represent the 29-byte IPv4/UDP encapsulation header
    # Offset 29 (temp daughter_a): 25 C (0x19)
    payload[29] = 0x19
    # Offset 30 (temp payload_3v3): 30 C (0x1e)
    payload[30] = 0x1E
    # Offset 35 (bus_3v3_volt_raw): 165 (0xa5)
    payload[35] = 0xA5
    # Offset 39 (user_cpu_time): 7200s (0x00001c20 big-endian)
    payload[39:43] = b"\x00\x00\x1c\x20"
    # Offset 63 (dir_data_free): 500 KB with KB bit 31 flag set (0x800001f4 big-endian)
    payload[63:67] = b"\x80\x00\x01\xf4"
    # Offset 79 (comms_rx_packets_raw): 5 (0x0005 big-endian) -> Expect 5 << 16 = 327680
    payload[79:81] = b"\x00\x05"

    return DecodedFrame(
        norad_id=68458,
        received_at=datetime.now(timezone.utc),
        src_callsign="KK6HIT",
        dest_callsign="EARTH",
        payload=bytes(payload),
        crc_valid=True,
    )


@pytest.fixture
def cape1_golden_frame() -> DecodedFrame:
    """Generate a valid ASCII-hex multiplexed frame for CAPE-1 (NORAD ID: 31130)."""
    # K5USL callsign + Type "1" packet + Hex strings:
    # mpb_voltage (off 6): "64" (100 -> 2.0V), hpb_voltage (off 8): "C8" (200 -> 4.0V)
    # battery_1_voltage (off 10): "FA" (250 -> 5.0V), dummy (off 12): "00"
    # battery_1_current_generated (off 14): "0A" (10 -> 10.0mA)
    payload_str = b"K5USL164C8FA000A" + (b"0" * 20)

    return DecodedFrame(
        norad_id=31130,
        received_at=datetime.now(timezone.utc),
        src_callsign="K5USL",
        dest_callsign="CQ",
        payload=payload_str,
        crc_valid=True,
    )


def test_demultiplex_oresat_golden_frame(oresat_golden_frame: DecodedFrame) -> None:
    """Verify little-endian structural unpacking and float casting for ORESAT0.5."""
    reading = demultiplex(oresat_golden_frame)
    
    assert reading.norad_id == 60525
    assert reading.received_at == oresat_golden_frame.received_at
    assert len(reading.metrics) == 6
    
    metrics = metrics_to_dict(reading)
    assert metrics["system_uptime"] == 3600.0
    assert metrics["system_unix_time"] == 1700000000.0
    assert metrics["system_power_cycles"] == 15.0
    assert metrics["system_storage_percent"] == 45.0
    assert metrics["battery_1_pack_1_vbatt"] == 8200.0
    assert metrics["battery_1_pack_1_vcell"] == 4100.0


def test_demultiplex_cp16_golden_frame(cp16_golden_frame: DecodedFrame) -> None:
    """Verify 29-byte IPv4/UDP header stripping and 16-bit shift bug resolution for SAL-E."""
    reading = demultiplex(cp16_golden_frame)
    
    assert reading.norad_id == 68458
    assert len(reading.metrics) == 6
    
    metrics = metrics_to_dict(reading)
    assert metrics["daughter_a_temp_raw"] == 25.0
    assert metrics["payload_3v3_temp_raw"] == 30.0
    assert metrics["bus_3v3_volt_raw"] == 165.0
    assert metrics["user_cpu_time"] == 7200.0
    assert metrics["dir_data_free_value"] == 500.0  # Stripped bit 31 KB flag
    assert metrics["comms_rx_packets"] == 327680.0  # 5 << 16 workaround verified


def test_demultiplex_cape1_golden_frame(cape1_golden_frame: DecodedFrame) -> None:
    """Verify K5USL callsign check, ASCII-hex decoding, and math scaling for CAPE-1."""
    reading = demultiplex(cape1_golden_frame)
    
    assert reading.norad_id == 31130
    assert len(reading.metrics) == 5
    
    metrics = metrics_to_dict(reading)
    assert metrics["packet_type"] == 1.0
    assert metrics["mpb_voltage"] == pytest.approx(2.0)
    assert metrics["hpb_voltage"] == pytest.approx(4.0)
    assert metrics["battery_1_voltage"] == pytest.approx(5.0)
    assert metrics["battery_1_current_generated"] == pytest.approx(10.0)


def test_demultiplex_rejects_invalid_crc(oresat_golden_frame: DecodedFrame) -> None:
    """Enforce Layer 2 boundary: frames with crc_valid=False must raise ValueError immediately."""
    corrupted_frame = DecodedFrame(
        norad_id=oresat_golden_frame.norad_id,
        received_at=oresat_golden_frame.received_at,
        src_callsign=oresat_golden_frame.src_callsign,
        dest_callsign=oresat_golden_frame.dest_callsign,
        payload=oresat_golden_frame.payload,
        crc_valid=False,  # Simulate CRC validation failure from signal processing stage
    )
    
    with pytest.raises(ValueError, match="Data integrity fault"):
        demultiplex(corrupted_frame)


def test_demultiplex_rejects_unregistered_norad_id(oresat_golden_frame: DecodedFrame) -> None:
    """Verify short-circuited rejection when an unsupported satellite NORAD ID is passed."""
    unsupported_frame = DecodedFrame(
        norad_id=99999,  # Unknown NORAD ID
        received_at=oresat_golden_frame.received_at,
        src_callsign="UNKNOWN",
        dest_callsign="EARTH",
        payload=oresat_golden_frame.payload,
        crc_valid=True,
    )
    
    with pytest.raises(ValueError, match="No structural demultiplexing spec registered"):
        demultiplex(unsupported_frame)


def test_demultiplex_rejects_empty_payload() -> None:
    """Verify short-circuited rejection when a DecodedFrame contains an empty payload."""
    empty_frame = DecodedFrame(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=b"",
        crc_valid=True,
    )
    
    with pytest.raises(ValueError, match="Cannot demultiplex an empty or invalid DecodedFrame"):
        demultiplex(empty_frame)
