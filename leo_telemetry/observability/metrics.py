"""Prometheus metric families for the observability track.

This module is the single registry schema for the pipeline (#21): every
metric family the exporter, tracker, or scorer publishes is declared
here, bound to one shared CollectorRegistry, so the scrape endpoint
serves a consistent, documented surface.

Labeling convention: every per-satellite family carries `norad_id` and
`satellite` (human-readable name, falling back to the NORAD id when the
satellite is not in TARGET_SATELLITES).
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge

from leo_telemetry.common.satellites import AUDIO_SATELLITES, TARGET_SATELLITES

# One registry for the whole service; passed to the scrape endpoint so
# the default global registry (with its python_* process metrics) does
# not leak unrelated series into the dashboard.
REGISTRY = CollectorRegistry()

_SATELLITE_NAMES = {
    sat.norad_id: sat.name for sat in TARGET_SATELLITES + AUDIO_SATELLITES
}


def satellite_label(norad_id: int) -> str:
    """Human-readable satellite name for a NORAD id, for the `satellite` label."""
    return _SATELLITE_NAMES.get(norad_id, str(norad_id))


TELEMETRY_METRIC = Gauge(
    "leo_telemetry_metric",
    "Latest value of one demultiplexed telemetry metric",
    labelnames=("norad_id", "satellite", "name", "unit"),
    registry=REGISTRY,
)

READINGS_TOTAL = Counter(
    "leo_telemetry_readings_total",
    "Telemetry readings exported since service start",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

LAST_READING_TIMESTAMP = Gauge(
    "leo_telemetry_last_reading_timestamp_seconds",
    "Unix time the satellite's most recent reading was received",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

READINESS_SCORE = Gauge(
    "leo_telemetry_readiness_score",
    "Composite mission readiness score in [0, 1] from the scoring track",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

QUEUE_DEPTH = Gauge(
    "leo_telemetry_queue_depth",
    "Pending items in each stage-to-stage Redis queue",
    labelnames=("queue",),
    registry=REGISTRY,
)

SATELLITE_LATITUDE = Gauge(
    "leo_telemetry_satellite_latitude_degrees",
    "Subpoint latitude of the satellite from Skyfield TLE propagation",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

SATELLITE_LONGITUDE = Gauge(
    "leo_telemetry_satellite_longitude_degrees",
    "Subpoint longitude of the satellite from Skyfield TLE propagation",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

SATELLITE_ALTITUDE = Gauge(
    "leo_telemetry_satellite_altitude_kilometers",
    "Altitude of the satellite above the WGS84 ellipsoid",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)

SATELLITE_VELOCITY = Gauge(
    "leo_telemetry_satellite_velocity_km_s",
    "Orbital speed of the satellite from Skyfield TLE propagation",
    labelnames=("norad_id", "satellite"),
    registry=REGISTRY,
)
