"""Helpers for feeding live decoded telemetry into the Prometheus exporter."""

from __future__ import annotations

from collections.abc import Iterable

from prometheus_client import CollectorRegistry, REGISTRY

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.observability.exporter import export


def export_from_frames(
    frames: Iterable[RawFrame],
    *,
    decode_func=decode_frame,
    demux_func=demultiplex,
    registry: CollectorRegistry | None = None,
) -> int:
    """Decode and demultiplex a batch of frames, then export any resulting readings."""
    target_registry = registry or REGISTRY
    exported = 0
    for frame in frames:
        decoded = decode_func(frame)
        if decoded is None:
            continue

        reading = demux_func(decoded)
        if reading is None:
            continue

        export(reading, registry=target_registry)
        exported += 1

    return exported
