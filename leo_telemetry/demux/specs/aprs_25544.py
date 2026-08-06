"""Implements APRS information-field parsing for the ISS (NORAD ID: 25544).

Reference: APRS Protocol Reference 1.0.1 (Tucson Amateur Packet Radio, 2000),
          chapters 5-9 and 13: data type identifiers, position report and
          telemetry report formats.

ISS frames on SatNOGS are AX.25 UI frames from the ARISS APRS digipeater:
the station's own Mic-E position beacons (RS0ISS / NA1SS) and amateur
traffic digipeated through it. Unlike the CubeSat specs this is a text
protocol, so the payload is classified by its APRS data type identifier
and position/telemetry fields are extracted where the format carries them
in the information field. Mic-E encodes latitude in the AX.25 destination
address, which is outside the payload, so Mic-E frames are classified and
counted but not position-decoded.

A decoded frame here does not report spacecraft health; its value is
proof the ARISS radio is alive and relaying. The readiness scorer treats
these metrics as non-health-relevant, so the ISS scores 1.0 whenever
frames flow, which is the honest reading of "the only thing this
downlink proves is that it works".
"""

from __future__ import annotations

import re

from leo_telemetry.common.models import TelemetryMetric

# APRS data type identifier -> (type name, numeric code)
_TYPE_CODES: dict[str, tuple[str, float]] = {
    "!": ("position", 1.0),
    "=": ("position", 1.0),
    "/": ("position_timestamped", 1.0),
    "@": ("position_timestamped", 1.0),
    "'": ("mic_e", 2.0),
    "`": ("mic_e", 2.0),
    ">": ("status", 3.0),
    ":": ("message", 4.0),
    "T": ("telemetry", 5.0),
    ";": ("object", 6.0),
    "_": ("weather", 7.0),
}

_POSITION_RE = re.compile(
    r"(?P<lat>\d{4}\.\d{2})(?P<ns>[NS]).(?P<lon>\d{5}\.\d{2})(?P<ew>[EW])"
)
_TELEMETRY_RE = re.compile(
    r"T#\d{1,3},(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3})"
)


def _aprs_degrees(value: str, hemisphere: str, *, lon: bool) -> float:
    """Convert APRS ddmm.mm / dddmm.mm text to signed decimal degrees."""
    split = 3 if lon else 2
    degrees = int(value[:split]) + float(value[split:]) / 60.0
    return -degrees if hemisphere in ("S", "W") else degrees


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """Classify an APRS information field and extract what it carries."""
    data = bytes(payload)
    if not data:
        raise ValueError("Empty APRS information field.")

    text = data.decode("latin-1")
    type_entry = _TYPE_CODES.get(text[0])
    if type_entry is None:
        raise ValueError(
            f"Unrecognized APRS data type identifier {text[0]!r}; dropping as RF noise."
        )
    _type_name, type_code = type_entry

    metrics: list[TelemetryMetric] = [
        TelemetryMetric("aprs_packet_type", type_code, "type"),
        TelemetryMetric("aprs_info_length", float(len(data)), "bytes"),
    ]

    if type_code == 1.0:
        match = _POSITION_RE.search(text)
        if match:
            metrics.extend(
                (
                    TelemetryMetric(
                        "aprs_station_latitude",
                        _aprs_degrees(match["lat"], match["ns"], lon=False),
                        "deg",
                    ),
                    TelemetryMetric(
                        "aprs_station_longitude",
                        _aprs_degrees(match["lon"], match["ew"], lon=True),
                        "deg",
                    ),
                )
            )

    if type_code == 5.0:
        match = _TELEMETRY_RE.search(text)
        if match:
            metrics.extend(
                TelemetryMetric(f"aprs_analog_{i}", float(v), "count")
                for i, v in enumerate(match.groups(), start=1)
            )

    return tuple(metrics)
