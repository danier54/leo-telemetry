from datetime import datetime, timezone

from leo_telemetry.common.models import RawFrame
from leo_telemetry.common.storage import _insert_params, _row_to_raw_frame


def _frame() -> RawFrame:
    return RawFrame(
        norad_id=60525,
        observation_id=1,
        observer_station_id=42,
        received_at=datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc),
        raw_bytes=b"\x7e\x00\x01\x7e",
    )


def test_insert_params_includes_dedup_key():
    frame = _frame()

    params = _insert_params(frame)

    assert params["norad_id"] == 60525
    assert params["observation_id"] == 1
    assert params["observer_station_id"] == 42
    assert params["received_at"] == frame.received_at
    assert params["raw_bytes"] == frame.raw_bytes
    assert params["dedup_key"] == frame.dedup_key


def test_row_to_raw_frame_round_trips_insert_params():
    frame = _frame()
    row = _insert_params(frame)
    row["raw_bytes"] = memoryview(row["raw_bytes"])  # psycopg returns buffer-like objects

    rebuilt = _row_to_raw_frame(row)

    assert rebuilt == frame
