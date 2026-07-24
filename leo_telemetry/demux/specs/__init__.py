"""Per-satellite byte layout specs, one module per NORAD ID/mission.

Each spec module should expose a function that takes a `bytes` payload and
returns a tuple of `TelemetryMetric` for that satellite's known telemetry
fields (battery voltage, CPU uptime, temperature, etc.), based on the
hardware documentation published by the satellite's maintainer.
"""


from __future__ import annotations

from typing import Callable

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs import cape1_31130, cp16_68458, oresat_60525

# Type alias for mission specification functions
SpecFunc = Callable[[bytes | memoryview], tuple[TelemetryMetric, ...]]

# Dispatch registry mapping NORAD ID to module functions
_MISSION_SPECS: dict[int, SpecFunc] = {
    60525: oresat_60525.demultiplex_payload,
    68458: cp16_68458.demultiplex_payload,
    31130: cape1_31130.demultiplex_payload,
}


def get_spec(norad_id: int) -> SpecFunc | None:
    """Retrieve the byte specification function for a given NORAD ID in O(1) time."""
    return _MISSION_SPECS.get(norad_id)


__all__ = ["get_spec", "SpecFunc"]