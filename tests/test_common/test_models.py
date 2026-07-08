from datetime import datetime, timezone

from leo_telemetry.common.models import RawFrame, TelemetryMetric, TelemetryReading


def test_raw_frame_dedup_key_is_stable_for_identical_frames():
    frame_a = RawFrame(
        norad_id=60525,
        observation_id=1,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
        raw_bytes=b"\x7e\x00\x01\x7e",
    )
    frame_b = RawFrame(
        norad_id=60525,
        observation_id=1,
        observer_station_id=99,
        received_at=datetime.now(timezone.utc),
        raw_bytes=b"\x7e\x00\x01\x7e",
    )

    assert frame_a.dedup_key == frame_b.dedup_key


def test_raw_frame_dedup_key_differs_for_different_payloads():
    base_kwargs = dict(
        norad_id=60525,
        observation_id=1,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
    )
    frame_a = RawFrame(raw_bytes=b"\x7e\x00\x01\x7e", **base_kwargs)
    frame_b = RawFrame(raw_bytes=b"\x7e\x00\x02\x7e", **base_kwargs)

    assert frame_a.dedup_key != frame_b.dedup_key


def test_telemetry_reading_holds_its_metrics():
    metric = TelemetryMetric(name="battery_voltage", value=7.4, unit="V")
    reading = TelemetryReading(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        metrics=(metric,),
    )

    assert reading.metrics[0].name == "battery_voltage"
