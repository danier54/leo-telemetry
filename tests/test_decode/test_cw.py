from __future__ import annotations

from datetime import datetime, timezone

import pytest

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.cw import decode_cw_beacon
from leo_telemetry.demux.demux import demultiplex


def _cw_frame(text: str) -> RawFrame:
    return RawFrame(
        norad_id=31130,
        observation_id=123,
        observer_station_id=7,
        received_at=datetime.now(timezone.utc),
        raw_bytes=text.encode("ascii"),
    )


def test_clean_beacon_normalizes_to_spec_payload():
    frame = decode_cw_beacon(_cw_frame("K5USL1A4FA96002D"))

    assert frame is not None
    assert frame.payload == b"K5USL1A4FA96002D"
    assert frame.src_callsign == "K5USL"


def test_spaced_cw_transcription_is_collapsed():
    frame = decode_cw_beacon(_cw_frame("K5USL 1 A4 FA 96 00 2D"))

    assert frame is not None
    assert frame.payload == b"K5USL1A4FA96002D"


def test_noise_transcription_is_dropped():
    # Real capture from the archive: the SatNOGS CW decoder transcribing
    # static as scattered dits and dahs.
    assert decode_cw_beacon(_cw_frame("SH T H E I E I E E ")) is None
    assert decode_cw_beacon(_cw_frame("E E I E E ")) is None


def test_missing_callsign_is_dropped():
    assert decode_cw_beacon(_cw_frame("1A4FA96002D")) is None


def test_unknown_packet_type_is_dropped():
    assert decode_cw_beacon(_cw_frame("K5USL9A4FA")) is None


def test_trailing_noise_after_hex_fields_is_trimmed():
    frame = decode_cw_beacon(_cw_frame("K5USL 2 0A F5 10 XYZ"))

    assert frame is not None
    assert frame.payload == b"K5USL20AF510"


def test_decode_frame_routes_cape1_to_cw_decoder():
    frame = decode_frame(_cw_frame("K5USL 1 A4 FA 96 00 2D"))

    assert frame is not None
    assert frame.payload == b"K5USL1A4FA96002D"


def test_decoded_beacon_demultiplexes_into_metrics():
    frame = decode_cw_beacon(_cw_frame("K5USL 2 0A F5 10"))
    reading = demultiplex(frame)

    assert reading is not None
    by_name = {m.name: m for m in reading.metrics}
    assert by_name["temp_battery_1"].value == 10.0
    assert by_name["temp_px_face"].value == -11.0
    assert by_name["temp_nx_face"].value == 16.0


def test_beacon_with_undecodable_fields_is_rejected_downstream() -> None:
    # Structure is present but too few hex chars for the type-1 layout;
    # decode accepts it, demux raises ValueError to route it to the DLQ.
    frame = decode_cw_beacon(_cw_frame("K5USL1A4"))

    assert frame is not None
    with pytest.raises(ValueError):
        demultiplex(frame)
