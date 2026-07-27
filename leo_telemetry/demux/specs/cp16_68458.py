"""Implements byte layout specifcation for SAL-E / CP16 (NORAD ID: 68458).

Reference: Libre Space Foundation. (2026). CP16 (SAL-E) 3U decoder struct. satnogs-decoders (Commit e93d1ef) [Source code]. GitLab. 
          https://gitlab.com/librespacefoundation/satnogs/satnogsdecoders/-/blob/e93d1ef4eb4f809fe0ef782fdef190555ffccae3/ksy/cp16.ksy
"""


from __future__ import annotations

import struct

from leo_telemetry.common.models import TelemetryMetric
from leo_telemetry.demux.specs.common import unpack_from_view

HEADER_LEN = 29

# Field Offsets/Schemas for SAL-E / CP16
OFFSET_TEMPS = 0
_TEMPS_STRUCT = struct.Struct(">BB")   # 2 bytes: Daughterboard and payload temps

OFFSET_BUS_VOLT = 6
_VOLT_STRUCT = struct.Struct(">B")     # 1 byte: 3.3V bus voltage

OFFSET_CPU_TIME = 10
_CPU_STRUCT = struct.Struct(">I")      # 4 bytes: User CPU time in seconds

OFFSET_DIR_FREE = 34
_DIR_STRUCT = struct.Struct(">I")      # 4 bytes: Available storage (bit 31 = unit flag)

OFFSET_RX_PKTS = 50
_PKTS_STRUCT = struct.Struct(">H")     # 2 bytes: Received comms packet count

# Compute required buffer size from the final layout boundary
MIN_DATA_LEN = OFFSET_RX_PKTS + _PKTS_STRUCT.size
MIN_PAYLOAD_LEN = HEADER_LEN + MIN_DATA_LEN

# Bitmasks
FLAG_DIR_UNIT_KB = 0x80000000          # Bit 31 high = Kilobytes; low = Bytes
MASK_DIR_VALUE = 0x7FFFFFFF            # Lower 31 bits hold the actual numeric value
SHIFT_RX_PKTS_OVERFLOW_FIX = 16        # Fix firmware truncating 32-bit counter to 16 bits documented in cp16.ksy


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """
    Map SAL-E / CP16 payload bytes to a tuple of typed physical metrics.

    Args:
        payload: Raw binary payload bytes or memory view.

    Returns:
        A tuple of extracted TelemetryMetric objects matching common.models.

    Raises:
        ValueError: If buffer overflows or is too short for header stripping.
    """
    if not payload or len(payload) < MIN_PAYLOAD_LEN:
        raise ValueError(
            f"CP16 buffer overflow: Required at least {MIN_PAYLOAD_LEN} bytes "
            f"({HEADER_LEN}-byte header + {MIN_DATA_LEN}-byte data), got {len(payload)}."
        )
    
    # Strip IPv4/UDP encapsulation header
    data = memoryview(payload)[HEADER_LEN:]

    (daughter_temp, payload_temp) = unpack_from_view(_TEMPS_STRUCT, data, OFFSET_TEMPS)
    (bus_volt,) = unpack_from_view(_VOLT_STRUCT, data, OFFSET_BUS_VOLT)
    (cpu_time,) = unpack_from_view(_CPU_STRUCT, data, OFFSET_CPU_TIME)
    (dir_raw,) = unpack_from_view(_DIR_STRUCT, data, OFFSET_DIR_FREE)
    (rx_pkts_raw,) = unpack_from_view(_PKTS_STRUCT, data, OFFSET_RX_PKTS)

    # Apply semantic bit masking and scaling
    is_kb = bool(dir_raw & FLAG_DIR_UNIT_KB)
    dir_free_val = dir_raw & MASK_DIR_VALUE
    fixed_rx_pkts = rx_pkts_raw << SHIFT_RX_PKTS_OVERFLOW_FIX

    return (
        TelemetryMetric("daughter_a_temp_raw", float(daughter_temp), "raw"),
        TelemetryMetric("payload_3v3_temp_raw", float(payload_temp), "raw"),
        TelemetryMetric("bus_3v3_volt_raw", float(bus_volt), "raw"),
        TelemetryMetric("user_cpu_time", float(cpu_time), "s"),
        TelemetryMetric("dir_data_free_value", float(dir_free_val), "KB" if is_kb else "bytes"),
        TelemetryMetric("comms_rx_packets", float(fixed_rx_pkts), "count"),
    )