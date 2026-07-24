"""Byte-offset to physical-unit mapping."""

from __future__ import annotations

from leo_telemetry.common.models import DecodedFrame, TelemetryReading
from leo_telemetry.demux import specs


def demultiplex(frame: DecodedFrame) -> TelemetryReading:
    """
    Map a decoded frame's payload bytes to typed telemetry metrics.

    Dispatches to the byte spec registered for `frame.norad_id` in
    `leo_telemetry.demux.specs`.

    Args:
        frame: Ingested frame containing NORAD ID, CRC status, timestamp, and raw payload.

    Returns:
        A TelemetryReading model populated with a tuple of extracted metrics.

    Raises:
        ValueError: If payload is invalid, CRC failed, or satellite has no registered spec.
    """
    # Prevent evaluation on empty or malformed objects
    if not frame or not getattr(frame, "payload", None):
        raise ValueError("Cannot demultiplex an empty or invalid DecodedFrame.")

    # Enforce Layer 2 data integrity
    if not frame.crc_valid:
        raise ValueError(
            f"Data integrity fault: Cannot demultiplex frame with invalid CRC-16 "
            f"checksum for NORAD ID {frame.norad_id}[cite: 2]."
        )

    # Mission spec lookup
    if (spec_func := specs.get_spec(frame.norad_id)) is None:
        raise ValueError(
            f"No structural demultiplexing spec registered for NORAD ID: {frame.norad_id}"
        )

    # Convert to zero-copy memoryview before passing down the pipeline
    payload_view = memoryview(frame.payload)

    return TelemetryReading(
        norad_id=frame.norad_id,
        received_at=frame.received_at,
        metrics=spec_func(payload_view),
    )