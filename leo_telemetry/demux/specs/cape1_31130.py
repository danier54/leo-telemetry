"""Implements byte layout specification for CAPE-1 (NORAD ID: 31130).

Reference: Libre Space Foundation. (2020). CAPE-1 decoder struct. satnogs-decoders (Commit 413aaf9) [Source code]. 
          https://gitlab.com/librespacefoundation/satnogs/satnogs-decoders/-/blob/e93d1ef4eb4f809fe0ef782fdef190555ffccae3/ksy/cape1.ksy
"""

from __future__ import annotations

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import parse_ascii_hex

# Protocol Framing
CALLSIGN_HEADER = b"K5USL"
HEADER_LEN = len(CALLSIGN_HEADER)
OFFSET_PKT_TYPE = 5
MIN_FRAME_LEN = 8                       # 5-byte callsign + 1-byte type + 2-byte min data

# Unit Scale Factors
SCALE_VOLTAGE = 0.02                    # 20mV per ADC bit
SCALE_PANEL_CURRENT = 10.0              # 10mA per ADC bit

# Power & Battery Generation offsets
OFFSET_T1_MPB_VOLT = 6
OFFSET_T1_HPB_VOLT = 8
OFFSET_T1_BATT1_VOLT = 10
OFFSET_T1_BATT1_CURR = 14

# Thermal Sensors 
OFFSET_T2_TEMP_BATT1 = 6
OFFSET_T2_TEMP_PX = 8
OFFSET_T2_TEMP_NX = 10

# Solar Panel Currents
OFFSET_T3_PANEL_PX_CURR = 6
OFFSET_T3_PANEL_NX_CURR = 8


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """Map CAPE-1 ASCII-hex multiplexed payload to typed physical metrics."""
    if not payload or len(payload) < MIN_FRAME_LEN or bytes(payload[:HEADER_LEN]) != CALLSIGN_HEADER:
        raise ValueError("Invalid CAPE-1 frame: Missing K5USL callsign header or buffer too short.")

    view = memoryview(payload)

    try:
        pkt_type = bytes(view[OFFSET_PKT_TYPE : OFFSET_PKT_TYPE + 1]).decode("ascii")
        pkt_type_num = float(int(pkt_type))
    
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid ASCII packet type indicator in CAPE-1 frame.") from exc

    metrics: list[TelemetryMetric] = [TelemetryMetric("packet_type", pkt_type_num, "type")]

    # Structural pattern matching for multiplexed ASCII routing
    match pkt_type:
        case "1":
            metrics.extend([
                TelemetryMetric("mpb_voltage", parse_ascii_hex(view, OFFSET_T1_MPB_VOLT, scale=SCALE_VOLTAGE), "V"),
                TelemetryMetric("hpb_voltage", parse_ascii_hex(view, OFFSET_T1_HPB_VOLT, scale=SCALE_VOLTAGE), "V"),
                TelemetryMetric("battery_1_voltage", parse_ascii_hex(view, OFFSET_T1_BATT1_VOLT, scale=SCALE_VOLTAGE), "V"),
                TelemetryMetric("battery_1_current_generated", parse_ascii_hex(view, OFFSET_T1_BATT1_CURR), "mA"),
            ])
        case "2":
            metrics.extend([
                TelemetryMetric("temp_battery_1", parse_ascii_hex(view, OFFSET_T2_TEMP_BATT1, signed=True), "C"),
                TelemetryMetric("temp_px_face", parse_ascii_hex(view, OFFSET_T2_TEMP_PX, signed=True), "C"),
                TelemetryMetric("temp_nx_face", parse_ascii_hex(view, OFFSET_T2_TEMP_NX, signed=True), "C"),
            ])
        case "3":
            metrics.extend([
                TelemetryMetric("panel_px_face_current", parse_ascii_hex(view, OFFSET_T3_PANEL_PX_CURR, scale=SCALE_PANEL_CURRENT), "mA"),
                TelemetryMetric("panel_nx_face_current", parse_ascii_hex(view, OFFSET_T3_PANEL_NX_CURR, scale=SCALE_PANEL_CURRENT), "mA"),
            ])
        case _:
            raise ValueError(f"Unknown CAPE-1 multiplexed packet type: '{pkt_type}'")

    return tuple(metrics)
