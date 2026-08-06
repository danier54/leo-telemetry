from __future__ import annotations

from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.demux.specs.sonate2_59112 import demultiplex_payload

# Real SONATE-2 downlink captured by SatNOGS on 2026-08-06T02:23:38Z:
# AX.25 (DP0SNX>CQ) carrying a CCSDS transfer frame, VCID 0, APID 100.
REAL_FRAME_HEX = (
    "86A240404040E088A060A69CB06103F02700C25218000864C9D100736A73EE98829836"
    "F22A7F46C00000000000096D91156FA728000000000000010800000C6222266800B1B0"
    "103534512A4E10415AD8C2C7C061B54B75605630D090DB1071920069436585670442006"
    "AC46704E8032E2A7F28FAA288028F92006840640073009A0067C06400F2804923000308"
    "0560802F2A"
)


def _real_raw_frame() -> RawFrame:
    return RawFrame(
        norad_id=59112,
        observation_id=1,
        observer_station_id=1,
        received_at=datetime(2026, 8, 6, 2, 23, 38, tzinfo=timezone.utc),
        raw_bytes=bytes.fromhex(REAL_FRAME_HEX),
    )


def test_real_frame_decodes_and_demultiplexes_end_to_end():
    decoded = decode_frame(_real_raw_frame())
    assert decoded is not None
    assert decoded.src_callsign == "DP0SNX"

    reading = demultiplex(decoded)
    assert reading is not None
    by_name = {m.name: m for m in reading.metrics}

    # Values transcribed from the published calibration polynomials
    # applied to this frame's raw counts.
    assert by_name["battery_5v1_voltage"].value == pytest.approx(4.215, abs=0.01)
    assert by_name["battery_5v2_voltage"].value == pytest.approx(4.235, abs=0.01)
    assert by_name["battery_12v1_voltage"].value == pytest.approx(4.111, abs=0.01)
    assert by_name["bus_12v1_voltage"].value == pytest.approx(11.944, abs=0.01)
    assert by_name["temp_battery_5v1"].value == pytest.approx(3.36, abs=0.1)
    assert by_name["temp_vhf1"].value == pytest.approx(1.0, abs=0.01)
    assert by_name["battery_5v1_current"].value == pytest.approx(358.2, abs=1.0)
    assert by_name["system_uptime"].unit == "s"


def test_non_housekeeping_virtual_channel_is_rejected():
    payload = bytearray(bytes.fromhex(REAL_FRAME_HEX)[16:])
    payload[1] = (payload[1] & ~0x0E) | (1 << 1)  # VCID 1: extended HK

    with pytest.raises(ValueError):
        demultiplex_payload(bytes(payload))


def test_short_frame_is_rejected():
    with pytest.raises(ValueError):
        demultiplex_payload(b"\x00" * 10)


def test_wrong_apid_is_rejected():
    payload = bytearray(bytes.fromhex(REAL_FRAME_HEX)[16:])
    payload[7] = 105  # APID low byte: OBDH EXT MEM OPS HK

    with pytest.raises(ValueError):
        demultiplex_payload(bytes(payload))
