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


def test_unregistered_apid_is_rejected():
    payload = bytearray(bytes.fromhex(REAL_FRAME_HEX)[16:])
    payload[7] = 106  # APID low byte: PDH PLDT HK, not yet mapped

    with pytest.raises(ValueError):
        demultiplex_payload(bytes(payload))


def _pack_bits(total_bytes: int, fields: list[tuple[int, int, int]]) -> bytes:
    """Inverse of _extract_bits: write MSB-first bit fields into a buffer."""
    buf = bytearray(total_bytes)
    for bit_pos, bit_len, value in fields:
        for i in range(bit_len):
            bit = bit_pos + i
            bit_value = (value >> (bit_len - 1 - i)) & 1
            if bit_value:
                buf[bit // 8] |= 1 << (7 - bit % 8)
    return bytes(buf)


def _mem_ops_hk_frame(*, vcid: int = 0) -> bytes:
    """Build a synthetic TF carrying APID 105 (OBDH EXT MEM OPS HK, 10B).

    Channel 1 and channel 4 (bit offsets 0 and 60, the first and last of
    the four 20-bit repeating blocks) are populated with distinct values
    to exercise the generated field table's stride math end to end;
    channels 2 and 3 are left at zero.
    """
    tf_header = bytearray(6)
    tf_header[1] = vcid << 1
    sp_header = bytes([0x00, 105, 0x00, 0x00, 0x00, 0x00])  # APID 105
    secondary_header = bytes(5)
    data = _pack_bits(
        10,
        [
            (0, 1, 1),   # obdh1 available
            (1, 3, 2),   # obdh1 state: RECEIVING
            (4, 8, 128), # obdh1 progress
            (12, 4, 9),  # obdh1 error code: SUCCESSFUL
            (16, 4, 3),  # obdh1 error count
            (60, 1, 1),   # obdh4 available
            (61, 3, 5),   # obdh4 state: BLANK CHECK
            (64, 8, 255), # obdh4 progress
            (72, 4, 12),  # obdh4 error code: FORBID ADDR
            (76, 4, 15),  # obdh4 error count
        ],
    )
    return bytes(tf_header) + sp_header + secondary_header + data


def test_mem_ops_hk_decodes_all_four_obdh_channels():
    metrics = demultiplex_payload(_mem_ops_hk_frame())

    assert len(metrics) == 20  # 4 channels x 5 fields
    by_name = {m.name: m for m in metrics}

    assert by_name["obdh1_mem_ops_available"].value == 1.0
    assert by_name["obdh1_mem_ops_available"].unit == "flag"
    assert by_name["obdh1_mem_ops_state"].value == 2.0
    assert by_name["obdh1_mem_ops_progress"].value == pytest.approx(50.2, abs=0.1)
    assert by_name["obdh1_mem_ops_error_code"].value == 9.0
    assert by_name["obdh1_mem_ops_error_count"].value == 3.0

    # Last channel (bit offset 60) confirms the 20-bit stride is applied
    # correctly all the way to the end of the 80-bit block.
    assert by_name["obdh4_mem_ops_available"].value == 1.0
    assert by_name["obdh4_mem_ops_state"].value == 5.0
    assert by_name["obdh4_mem_ops_progress"].value == pytest.approx(100.0, abs=0.1)
    assert by_name["obdh4_mem_ops_error_code"].value == 12.0
    assert by_name["obdh4_mem_ops_error_count"].value == 15.0

    # Untouched channels decode cleanly as all-zero rather than raising.
    assert by_name["obdh2_mem_ops_available"].value == 0.0
    assert by_name["obdh3_mem_ops_state"].value == 0.0


def test_mem_ops_hk_rejects_non_housekeeping_vcid():
    with pytest.raises(ValueError):
        demultiplex_payload(_mem_ops_hk_frame(vcid=1))
