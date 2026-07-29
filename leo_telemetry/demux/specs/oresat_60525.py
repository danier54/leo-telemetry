"""Implements byte layout specification for ORESAT0.5 (NORAD ID: 60525).

Reference: Libre Space Foundation. (2024). Oresat0_5 decoder struct. satnogs-decoders (Commit 8b694c) [Source code].
          https://gitlab.com/librespacefoundation/satnogs/satnogs-decoders/-/blob/e93d1ef4eb4f809fe0ef782fdef190555ffccae3/ksy/oresat0_5.ksy
"""

from __future__ import annotations

import struct

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import unpack_from_view

# Protocol Framing
PID_HEADER_LEN = 1
RAW_FRAME_LEN_WITH_PID = 217           # Standard 216-byte Oresat data payload + 1-byte AX.25 PID

# Field Offsets/Schemas
OFFSET_SYS_METRICS = 7
_SYS_STRUCT = struct.Struct("<IIHB")   # 11 bytes: Uptime, unix time, power cycles, storage pct

OFFSET_BATT_METRICS = 49
_BATT_STRUCT = struct.Struct("<HH")    # 4 bytes: Battery pack voltage and cell voltage

# Derive boundary check from the last field's address and size
MIN_DATA_LEN = OFFSET_BATT_METRICS + _BATT_STRUCT.size


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """Map ORESAT0.5 payload bytes to a tuple of typed physical metrics."""
    if not payload:
        raise ValueError("Cannot decode an empty ORESAT0.5 payload buffer.")

    # Strip optional 1-byte PID header if present
    view = memoryview(payload)
    data = view[PID_HEADER_LEN:] if len(view) == RAW_FRAME_LEN_WITH_PID else view

    if len(data) < MIN_DATA_LEN:
        raise ValueError(f"ORESAT0.5 buffer overflow: Required {MIN_DATA_LEN} bytes, got {len(data)}.")

    uptime, unix_time, pwr_cycles, storage_pct = unpack_from_view(_SYS_STRUCT, data, OFFSET_SYS_METRICS)
    vbatt, vcell = unpack_from_view(_BATT_STRUCT, data, OFFSET_BATT_METRICS)

    return (
        TelemetryMetric("system_uptime", float(uptime), "s"),
        TelemetryMetric("system_unix_time", float(unix_time), "s"),
        TelemetryMetric("system_power_cycles", float(pwr_cycles), "count"),
        TelemetryMetric("system_storage_percent", float(storage_pct), "%"),
        TelemetryMetric("battery_1_pack_1_vbatt", float(vbatt), "mV"),
        TelemetryMetric("battery_1_pack_1_vcell", float(vcell), "mV"),
    )