import subprocess
import sys
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


def test_raw_frame_dedup_key_is_stable_across_process_restarts():
    """Guards against relying on Python's builtin hash(), which is
    randomly seeded per-process and would make every frame look "new"
    again after a pod restart even though the bytes are identical."""
    script = (
        "from leo_telemetry.common.models import RawFrame; "
        "from datetime import datetime, timezone; "
        "print(RawFrame("
        "norad_id=60525, observation_id=1, observer_station_id=42, "
        "received_at=datetime.now(timezone.utc), raw_bytes=b'\\x7e\\x00\\x01\\x7e'"
        ").dedup_key)"
    )

    def run_with_seed(seed: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    assert run_with_seed("1") == run_with_seed("2")


def test_telemetry_reading_holds_its_metrics():
    metric = TelemetryMetric(name="battery_voltage", value=7.4, unit="V")
    reading = TelemetryReading(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        metrics=(metric,),
    )

    assert reading.metrics[0].name == "battery_voltage"
