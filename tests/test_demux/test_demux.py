from __future__ import annotations

from datetime import datetime, timezone
import pytest

from leo_telemetry.common.models import DecodedFrame, TelemetryReading
from leo_telemetry.demux.demux import demultiplex


def _frame(norad_id: int, payload: bytes, crc_valid: bool = True) -> DecodedFrame:
    return DecodedFrame(
        norad_id=norad_id,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=payload,
        crc_valid=crc_valid,
    )


# Mock payloads/synthetic test vectors to assert parser correctly extracts offsets
def _oresat_payload() -> bytes:
    payload = bytearray(216)
    payload[7:11] = b"\x10\x0e\x00\x00"   # uptime: 3600s (little-endian)
    payload[11:15] = b"\x00\xf1\x53\x65"  # unix time: 1700000000s (little-endian)
    payload[15:17] = b"\x0f\x00"          # power cycles: 15
    payload[17:18] = b"\x2d"              # storage: 45%
    payload[49:51] = b"\x08\x20"          # vbatt: 8200 mV
    payload[51:53] = b"\x04\x10"          # vcell: 4100 mV
    return bytes(payload)


def _cp16_payload() -> bytes:
    payload = bytearray(90)
    payload[29] = 0x19                    # daughter_a: 25 C (after 29-byte IPv4/UDP header)
    payload[30] = 0x1E                    # payload_3v3: 30 C
    payload[35] = 0xA5                    # bus_3v3_volt_raw: 165
    payload[39:43] = b"\x00\x00\x1c\x20"  # cpu_time: 7200s (big-endian)
    payload[63:67] = b"\x80\x00\x01\xf4"  # dir_data_free: 500 KB with bit 31 flag set
    payload[79:81] = b"\x00\x05"          # comms_rx_packets: 5 (expects 5 << 16 = 327680)
    return bytes(payload)


def metrics_to_dict(reading: TelemetryReading) -> dict[str, tuple[float, str]]:
    return {m.name: (m.value, m.unit) for m in reading.metrics}


def test_demultiplex_oresat_synthetic_payload():
    reading = demultiplex(_frame(60525, _oresat_payload()))
    assert reading is not None
    assert reading.norad_id == 60525
    assert len(reading.metrics) == 6
    
    metrics = metrics_to_dict(reading)
    assert metrics["system_uptime"] == (3600.0, "s")
    assert metrics["system_unix_time"] == (1700000000.0, "s")
    assert metrics["system_power_cycles"] == (15.0, "count")
    assert metrics["system_storage_percent"] == (45.0, "%")
    assert metrics["battery_1_pack_1_vbatt"] == (8200.0, "mV")
    assert metrics["battery_1_pack_1_vcell"] == (4100.0, "mV")


def test_demultiplex_cp16_synthetic_payload():
    reading = demultiplex(_frame(68458, _cp16_payload()))
    assert reading is not None
    assert reading.norad_id == 68458
    assert len(reading.metrics) == 6
    
    metrics = metrics_to_dict(reading)
    assert metrics["daughter_a_temp_raw"] == (25.0, "raw")
    assert metrics["payload_3v3_temp_raw"] == (30.0, "raw")
    assert metrics["bus_3v3_volt_raw"] == (165.0, "raw")
    assert metrics["user_cpu_time"] == (7200.0, "s")
    assert metrics["dir_data_free_value"] == (500.0, "KB")
    assert metrics["comms_rx_packets"] == (327680.0, "count")


def test_demultiplex_cape1_synthetic_payload():
    payload = b"K5USL164C8FA000A" + (b"0" * 20)
    reading = demultiplex(_frame(31130, payload))
    assert reading is not None
    assert reading.norad_id == 31130
    assert len(reading.metrics) == 5
    
    metrics = metrics_to_dict(reading)
    assert metrics["packet_type"] == (1.0, "type")
    assert metrics["mpb_voltage"] == pytest.approx((2.0, "V"))
    assert metrics["hpb_voltage"] == pytest.approx((4.0, "V"))
    assert metrics["battery_1_voltage"] == pytest.approx((5.0, "V"))
    assert metrics["battery_1_current_generated"] == pytest.approx((10.0, "mA"))


def test_demultiplex_rejects_invalid_crc():
    assert demultiplex(_frame(60525, _oresat_payload(), crc_valid=False)) is None


def test_demultiplex_rejects_unregistered_norad_id():
    assert demultiplex(_frame(99999, _oresat_payload())) is None


def test_demultiplex_rejects_empty_payload():
    assert demultiplex(_frame(60525, b"")) is None