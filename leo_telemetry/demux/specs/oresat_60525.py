# Author: Taurean Newsome
# OSU Email: newsotau@oregonstate.edu
# Gitzhub username: newtau
# Description: Implements per-satellite byte layotu specificsation for ORESAT0.5 
#              (NORAD ID: 60525).


from __future__ import annotations

import struct

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import unpack_from_view

# Pre-compiled little-endian C-struct schemas for constant time unpacking
_SYS_STRUCT = struct.Struct("<IIHB")  # Offsets 7..17
_BATT_STRUCT = struct.Struct("<HH")    # Offsets 49..52


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """
    Map ORESAT0.5 payload bytes to a tuple of typed physical metrics.

    Args:
        payload: Raw AX.25 UI/I-frame payload bytes or memory view.

    Returns:
        A tuple of extracted TelemetryMetric objects matching common.models.

    Raises:
        ValueError: If buffer overflows or fails structural validation checks.
    """
    if not payload:
        raise ValueError("Cannot decode an empty ORESAT0.5 payload buffer.")

    # Strip optional 1-byte PID header if present
    view = memoryview(payload)
    data = view[1:] if len(view) == 217 else view

    if len(data) < 53:
        raise ValueError(f"ORESAT0.5 buffer overflow: Required 53 bytes, got {len(data)}.")

    uptime, unix_time, pwr_cycles, storage_pct = unpack_from_view(_SYS_STRUCT, data, 7)
    vbatt, vcell = unpack_from_view(_BATT_STRUCT, data, 49)

    return (
        TelemetryMetric("system_uptime", float(uptime), "s"),
        TelemetryMetric("system_unix_time", float(unix_time), "s"),
        TelemetryMetric("system_power_cycles", float(pwr_cycles), "count"),
        TelemetryMetric("system_storage_percent", float(storage_pct), "%"),
        TelemetryMetric("battery_1_pack_1_vbatt", float(vbatt), "mV"),
        TelemetryMetric("battery_1_pack_1_vcell", float(vcell), "mV"),
    )
