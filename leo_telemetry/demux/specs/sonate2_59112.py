"""Implements the CCSDS frame layout for SONATE-2 (NORAD ID: 59112).

Reference: University of Wuerzburg. SONATE-2 protocol definition for radio
          amateurs (SONATE-2_protocol_definition_for_radio_amateurs.xlsx).
          https://www.informatik.uni-wuerzburg.de/en/space-technology/projects/active/sonate-2/information-for-radio-amateurs/

The AX.25 information field carries a CCSDS TM Transfer Frame:

    TFHead (6B) | Space Packet: SPHead (6B) + secondary header (5B) +
    DATA (per APID) | ... | FECF CRC-16 (2B)

Virtual channels 0/2 carry Standard Housekeeping and 1/3 carry Extended
Housekeeping (VCID meanings per the General sheet); binary-download
channels 4-7 are dropped. Each registered APID is only valid on its own
housekeeping channel pair, checked below. Field bit positions and
calibration polynomials are transcribed from the DATA definition sheet.
Two APIDs are registered:

    100  STD HK       -- power, battery, and radio health (the frequent
                          beacon; this is what the dashboard's readiness
                          score is computed from). VCID 0/2 only.
    105  OBDH EXT MEM OPS HK -- onboard-computer memory operation status
                          for each of the four redundant OBDH channels.
                          VCID 1/3 only (it's an "EXT" -- Extended
                          Housekeeping -- APID, not Standard).

Other APIDs (extended error codes, memory status, LEOP housekeeping, and
so on) are not yet mapped; demultiplex_payload() raises ValueError for
them so unmapped frames are dropped rather than misread.
"""

from __future__ import annotations

from leo_telemetry.common.models import TelemetryMetric

TF_HEADER_LEN = 6
SP_HEADER_LEN = 6
SECONDARY_HEADER_LEN = 5
STD_HK_VCIDS = (0, 2)
EXT_HK_VCIDS = (1, 3)
MIN_TF_LEN = TF_HEADER_LEN + SP_HEADER_LEN + SECONDARY_HEADER_LEN + 2

APID_STD_HK = 100
APID_MEM_OPS_HK = 105

# A field is (name, unit, bit position, bit length, calibration polynomial
# coefficients (c0 + c1*x + c2*x^2), output scale). Units "state" and
# "flag" report the raw enum/boolean code rather than a decoded string,
# matching how other specs in this package expose classification fields
# (see cp16_68458.packet_type).
_Field = tuple[str, str, int, int, tuple[float, float, float], float]

_STD_HK_FIELDS: tuple[_Field, ...] = (
    ("system_uptime",         "s", 0,   24, (0.0, 1.0, 0.0), 1.0),
    ("temp_vhf1",             "C", 299, 8,  (-128.0, 1.0, 0.0), 1.0),
    ("temp_uhf1",             "C", 402, 8,  (-128.0, 1.0, 0.0), 1.0),
    ("battery_5v1_voltage",   "V", 513, 8,  (0.0, 0.020070588, 0.0), 1.0),
    # Battery current is calibrated in amps; exported in mA to match the
    # other specs' current convention.
    ("battery_5v1_current",   "mA", 521, 8, (-7.641924759, 0.059702537, 0.0), 1000.0),
    ("bus_5v1_voltage",       "V", 545, 8,  (0.0, 0.024530719, 0.0), 1.0),
    ("battery_5v2_voltage",   "V", 577, 8,  (0.0, 0.019882353, 0.0), 1.0),
    ("temp_battery_5v1",      "C", 625, 8,  (-47.23889465, 0.548218308, 0.0000195267), 1.0),
    ("temp_battery_12v1",     "C", 633, 8,  (-43.91789355, 0.534063389, 0.0000128733), 1.0),
    ("battery_12v1_voltage",  "V", 713, 8,  (0.0, 0.019764706, 0.0), 1.0),
    ("bus_12v1_voltage",      "V", 745, 8,  (0.0, 0.051930796, 0.0), 1.0),
    ("solar_reg_12v1_state",  "state", 825, 2, (0.0, 1.0, 0.0), 1.0),
)


def _mem_ops_channel_fields(channel: int) -> tuple[_Field, ...]:
    """Build the five-field, 20-bit memory-ops block for one OBDH channel.

    The four OBDH channels (1-4) repeat an identical 20-bit block at a
    fixed 20-bit stride: available flag, state enum, progress percent,
    error code enum, error count. Generating the table from this shared
    layout avoids hand-transcribing the same five fields four times.
    """
    base = (channel - 1) * 20
    prefix = f"obdh{channel}_mem_ops"
    return (
        (f"{prefix}_available", "flag", base, 1, (0.0, 1.0, 0.0), 1.0),
        (f"{prefix}_state", "state", base + 1, 3, (0.0, 1.0, 0.0), 1.0),
        (f"{prefix}_progress", "%", base + 4, 8, (0.0, 0.3921568627, 0.0), 1.0),
        (f"{prefix}_error_code", "state", base + 12, 4, (0.0, 1.0, 0.0), 1.0),
        (f"{prefix}_error_count", "count", base + 16, 4, (0.0, 1.0, 0.0), 1.0),
    )


_MEM_OPS_HK_FIELDS: tuple[_Field, ...] = tuple(
    field for channel in (1, 2, 3, 4) for field in _mem_ops_channel_fields(channel)
)

_APID_FIELDS: dict[int, tuple[_Field, ...]] = {
    APID_STD_HK: _STD_HK_FIELDS,
    APID_MEM_OPS_HK: _MEM_OPS_HK_FIELDS,
}

# Each APID only appears on its own housekeeping channel pair -- Standard
# HK APIDs on VCID 0/2, Extended HK APIDs (like the mem-ops block) on
# VCID 1/3. Checked in demultiplex_payload() once the APID is known.
_APID_VCIDS: dict[int, tuple[int, ...]] = {
    APID_STD_HK: STD_HK_VCIDS,
    APID_MEM_OPS_HK: EXT_HK_VCIDS,
}


def _extract_bits(data: memoryview, bit_pos: int, bit_len: int) -> int:
    """Read an MSB-first big-endian bit field, per CCSDS conventions."""
    end_byte = (bit_pos + bit_len + 7) // 8
    if end_byte > len(data):
        raise ValueError(
            f"Bit field [{bit_pos}:{bit_pos + bit_len}] out of bounds for "
            f"{len(data)}-byte packet data."
        )
    value = 0
    for i in range(bit_len):
        bit = bit_pos + i
        value = (value << 1) | ((data[bit // 8] >> (7 - bit % 8)) & 1)
    return value


def _decode_fields(data: memoryview, fields: tuple[_Field, ...]) -> tuple[TelemetryMetric, ...]:
    """Apply each field's calibration polynomial and return typed metrics."""
    return tuple(
        TelemetryMetric(name, (c0 + c1 * x + c2 * x * x) * scale, unit)
        for name, unit, bit_pos, bit_len, (c0, c1, c2), scale in fields
        for x in (float(_extract_bits(data, bit_pos, bit_len)),)
    )


def demultiplex_payload(payload: bytes | memoryview) -> tuple[TelemetryMetric, ...]:
    """Map a SONATE-2 transfer frame to typed physical metrics."""
    view = memoryview(payload)
    if len(view) < MIN_TF_LEN:
        raise ValueError("SONATE-2 transfer frame shorter than minimum layout.")

    vcid = (view[1] >> 1) & 0x7

    first_header_pointer = ((view[4] & 0x07) << 8) | view[5]
    packet_start = TF_HEADER_LEN + first_header_pointer
    if packet_start + SP_HEADER_LEN > len(view):
        raise ValueError("SONATE-2 first header pointer past end of frame.")

    sp = view[packet_start:]
    apid = ((sp[0] & 0x07) << 8) | sp[1]
    fields = _APID_FIELDS.get(apid)
    if fields is None:
        raise ValueError(f"SONATE-2 APID {apid} has no registered field map.")

    # VCID validity depends on which APID we found -- Standard HK APIDs
    # only appear on VCID 0/2, Extended HK APIDs only on VCID 1/3.
    if vcid not in _APID_VCIDS[apid]:
        raise ValueError(f"SONATE-2 APID {apid} is not expected on VCID {vcid}.")

    data = sp[SP_HEADER_LEN + SECONDARY_HEADER_LEN :]
    return _decode_fields(data, fields)
