"""Byte-offset to physical-unit mapping."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, TelemetryReading


def demultiplex(frame: DecodedFrame) -> TelemetryReading:
    """Map a decoded frame's payload bytes to typed telemetry metrics.

    Dispatches to the byte spec registered for `frame.norad_id` in
    `leo_telemetry.demux.specs`.
    """
    raise NotImplementedError
