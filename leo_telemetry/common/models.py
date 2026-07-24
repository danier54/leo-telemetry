"""Data contracts passed between pipeline stages.

These types are the interface boundary between the four tracks:

    ingest -> RawFrame -> decode -> DecodedFrame -> demux -> TelemetryReading -> observability

Changing a field here affects whoever consumes it downstream, so changes
should be agreed on by both the producing and consuming track owners.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class RawFrame:
    """
    A single raw telemetry frame as received from SatNOGS, pre-decode.

    Produced by: ingest
    Consumed by: decode
    """

    norad_id: int
    observation_id: int
    observer_station_id: int
    received_at: datetime
    raw_bytes: bytes

    @property
    def dedup_key(self) -> str:
        """
        Stable key used to drop duplicate captures from overlapping ground stations.

        Uses sha256 rather than the builtin `hash()`, which is seeded
        randomly per process and would otherwise make every frame look
        "new" again after each restart.
        """
        digest = hashlib.sha256(self.raw_bytes).hexdigest()
        return f"{self.norad_id}:{self.observation_id}:{digest}"


@dataclass(frozen=True)
class DecodedFrame:
    """
    An AX.25 frame after frame sync, bit-destuffing, and CRC-16 validation.

    Produced by: decode
    Consumed by: demux
    """

    norad_id: int
    received_at: datetime
    src_callsign: str
    dest_callsign: str
    payload: bytes
    crc_valid: bool


@dataclass(frozen=True)
class TelemetryMetric:
    """A single named, typed, physical measurement extracted from a payload."""

    name: str
    value: float
    unit: str


@dataclass(frozen=True)
class TelemetryReading:
    """
    The full set of demultiplexed metrics for one decoded frame.

    Produced by: demux
    Consumed by: observability (Prometheus exporter) and scoring
    """

    norad_id: int
    received_at: datetime
    metrics: tuple[TelemetryMetric, ...] = field(default_factory=tuple)
