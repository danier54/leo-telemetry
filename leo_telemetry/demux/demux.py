"""Byte-offset to physical-unit mapping."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, TelemetryReading
from leo_telemetry.demux import specs


def demultiplex(frame: DecodedFrame) -> TelemetryReading | None:
    """
    Map a decoded frame's payload bytes to typed telemetry metrics.

    Dispatches to the byte spec registered for `frame.norad_id` in
    `leo_telemetry.demux.specs`.

    Args:
        frame: Ingested frame containing NORAD ID, CRC status, timestamp, and raw payload.

    Returns:
        A TelemetryReading model populated with a tuple of extracted metrics,
        or None if the frame is empty, CRC failed, or the satellite has no registered spec.
        
    Raises:
        ValueError: If struct unpacking or ASCII-hex parsing overflows.
    """
    # Prevent evaluation on empty or malformed objects
    if not frame or not getattr(frame, "payload", None):
        return None

    # Enforce Layer 2 data integrity
    if not frame.crc_valid:
        return None

    # Mission spec lookup
    if (spec_func := specs.get_spec(frame.norad_id)) is None:
        return None

    # Convert to zero-copy memoryview before passing down the pipeline
    payload_view = memoryview(frame.payload)

    # Allow ValueErrors to bubble up to run.py for routing to the DLQ
    return TelemetryReading(
        norad_id=frame.norad_id,
        received_at=frame.received_at,
        metrics=spec_func(payload_view),
    )