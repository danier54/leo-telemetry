
# Author: Taurean Newsome
# OSU Email: newsotau@oregonstate.edu
# Gitzhub username: newtau
# Description: Implements Per-satellite byte layout spec for SAL-E / CP16 
#              (NORAD ID: 68458).


from __future__ import annotations

import struct

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import unpack_from_view

# Pre-compiled big-endian C-struct schemas
_TEMPS_STRUCT = struct.Struct(">BB")  # Offset 0
_VOLT_STRUCT = struct.Struct(">B")    # Offset 6
_CPU_STRUCT = struct.Struct(">I")     # Offset 10
_DIR_STRUCT = struct.Struct(">I")     # Offset 34
_PKTS_STRUCT = struct.Struct(">H")    # Offset 50


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """
    Map SAL-E / CP16 payload bytes to a tuple of typed physical metrics, 
    resolving documented bit-shift bugs.

    Args:
        payload: Raw binary payload bytes or memory view[cite: 2].

    Returns:
        A tuple of extracted TelemetryMetric objects matching common.models.

    Raises:
        ValueError: If buffer overflows or is too short for header stripping.
    """
    if not payload or len(payload) < 52:
        raise ValueError(f"CP16 buffer overflow: Required 52 bytes, got {len(payload)}.")

    # Strip the 29-byte IPv4/UDP encapsulation header
    data = memoryview(payload)[29:]

    (daughter_temp, payload_temp) = unpack_from_view(_TEMPS_STRUCT, data, 0)
    (bus_volt,) = unpack_from_view(_VOLT_STRUCT, data, 6)
    (cpu_time,) = unpack_from_view(_CPU_STRUCT, data, 10)
    (dir_raw,) = unpack_from_view(_DIR_STRUCT, data, 34)
    (rx_pkts_raw,) = unpack_from_view(_PKTS_STRUCT, data, 50)

    # Resolve custom bitmasking for directory space (bit 31 flag = KB)
    is_kb = bool(dir_raw & 0x80000000)
    dir_free_val = dir_raw & 0x7FFFFFFF

    return (
        TelemetryMetric("daughter_a_temp_raw", float(daughter_temp), "raw"),
        TelemetryMetric("payload_3v3_temp_raw", float(payload_temp), "raw"),
        TelemetryMetric("bus_3v3_volt_raw", float(bus_volt), "raw"),
        TelemetryMetric("user_cpu_time", float(cpu_time), "s"),
        TelemetryMetric("dir_data_free_value", float(dir_free_val), "KB" if is_kb else "bytes"),
        TelemetryMetric("comms_rx_packets", float(rx_pkts_raw << 16), "count"),  # Lossy bug fix[cite: 2]
    )