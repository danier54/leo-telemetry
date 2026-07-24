# Author: Taurean Newsome
# OSU Email: newsotau@oregonstate.edu
# Gitzhub username: newtau
# Description: Implements per-satellite byte layout spec for CAPE-1 (NORAD ID: 31130).


from __future__ import annotations

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import parse_ascii_hex


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """
    Map CAPE-1 ASCII-hex multiplexed payload to typed physical metrics.

    Args:
        payload: Raw custom framing bytes or memory view.

    Returns:
        A tuple of extracted TelemetryMetric objects matching common.models.

    Raises:
        ValueError: If missing K5USL header or unknown packet type is encountered.
    """
    if not payload or len(payload) < 8 or bytes(payload[:5]) != b"K5USL":
        raise ValueError("Invalid CAPE-1 frame: Missing K5USL callsign header.")

    view = memoryview(payload)
    try:
        pkt_type = str(bytes(view[5:6]), encoding="ascii")
        pkt_type_num = float(int(pkt_type))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid ASCII packet type indicator in CAPE-1 frame.") from exc

    metrics: list[TelemetryMetric] = [TelemetryMetric("packet_type", pkt_type_num, "type")]

    # Sructural pattern matching for multiplexed ASCII routing
    match pkt_type:
        case "1":
            metrics.extend([
                TelemetryMetric("mpb_voltage", parse_ascii_hex(view, 6, scale=0.02), "V"),
                TelemetryMetric("hpb_voltage", parse_ascii_hex(view, 8, scale=0.02), "V"),
                TelemetryMetric("battery_1_voltage", parse_ascii_hex(view, 10, scale=0.02), "V"),
                TelemetryMetric("battery_1_current_generated", parse_ascii_hex(view, 14), "mA"),
            ])
        case "2":
            metrics.extend([
                TelemetryMetric("temp_battery_1", parse_ascii_hex(view, 6, signed=True), "C"),
                TelemetryMetric("temp_px_face", parse_ascii_hex(view, 8, signed=True), "C"),
                TelemetryMetric("temp_nx_face", parse_ascii_hex(view, 10, signed=True), "C"),
            ])
        case "3":
            metrics.extend([
                TelemetryMetric("panel_px_face_current", parse_ascii_hex(view, 6, scale=10.0), "mA"),
                TelemetryMetric("panel_nx_face_current", parse_ascii_hex(view, 8, scale=10.0), "mA"),
            ])
        case _:
            raise ValueError(f"Unknown CAPE-1 multiplexed packet type: '{pkt_type}'[cite: 2]")

    return tuple(metrics)