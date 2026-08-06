from __future__ import annotations

from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.demux.specs.aprs_25544 import demultiplex_payload

# Real ISS downlinks captured by SatNOGS:
# a ham position report digipeated through ARISS (KM7DOS, 2026-08-04)
POSITION_FRAME_HEX = (
    "82A0929C646460969A6E889EA66082A492A6A6406103F021343732322E30304E2F3132"
    "3230342E33385764435120434E383720436F76696E67746F6E205741"
)
# and the station's own Mic-E beacon (RS0ISS, 2026-07-31)
MIC_E_FRAME_HEX = (
    "60A060A0A66860A4A66092A6A6E082A0A4A682A86103F02776261C6C201C53495D4152"
    "4953532D496E7465726E6174696F6E616C2053706163652053746174696F6E3D0D"
)


def _raw(frame_hex: str) -> RawFrame:
    return RawFrame(
        norad_id=25544,
        observation_id=1,
        observer_station_id=1,
        received_at=datetime(2026, 8, 4, 0, 15, 41, tzinfo=timezone.utc),
        raw_bytes=bytes.fromhex(frame_hex),
    )


def test_digipeated_position_report_decodes_end_to_end():
    decoded = decode_frame(_raw(POSITION_FRAME_HEX))
    assert decoded is not None
    assert decoded.src_callsign == "KM7DOS"

    reading = demultiplex(decoded)
    assert reading is not None
    by_name = {m.name: m for m in reading.metrics}
    assert by_name["aprs_packet_type"].value == 1.0
    # "!4722.00N/12204.38W" -> Covington WA
    assert by_name["aprs_station_latitude"].value == pytest.approx(47.3667, abs=0.001)
    assert by_name["aprs_station_longitude"].value == pytest.approx(-122.073, abs=0.001)


def test_iss_mic_e_beacon_is_classified_without_position():
    decoded = decode_frame(_raw(MIC_E_FRAME_HEX))
    assert decoded is not None
    assert decoded.src_callsign == "RS0ISS"

    reading = demultiplex(decoded)
    assert reading is not None
    by_name = {m.name: m for m in reading.metrics}
    assert by_name["aprs_packet_type"].value == 2.0  # Mic-E
    assert "aprs_station_latitude" not in by_name


def test_telemetry_report_extracts_analog_channels():
    metrics = demultiplex_payload(b"T#005,199,000,255,073,123,01101001")

    by_name = {m.name: m for m in metrics}
    assert by_name["aprs_packet_type"].value == 5.0
    assert by_name["aprs_analog_1"].value == 199.0
    assert by_name["aprs_analog_3"].value == 255.0
    assert by_name["aprs_analog_5"].value == 123.0


def test_rf_noise_is_rejected():
    with pytest.raises(ValueError):
        demultiplex_payload(b"\xe6} \x0e\xee")
    with pytest.raises(ValueError):
        demultiplex_payload(b"")
