from datetime import datetime, timezone

from leo_telemetry.common.models import RawFrame
from leo_telemetry.ingest.dedup import DedupQueue


def _frame(observation_id: int) -> RawFrame:
    return RawFrame(
        norad_id=60525,
        observation_id=observation_id,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
        raw_bytes=b"\x7e\x00\x01\x7e",
    )


def test_push_accepts_first_occurrence():
    queue = DedupQueue()

    assert queue.push(_frame(1)) is True
    assert len(queue) == 1


def test_push_rejects_duplicate():
    queue = DedupQueue()
    queue.push(_frame(1))

    assert queue.push(_frame(1)) is False
    assert len(queue) == 1


def test_pop_returns_frames_in_fifo_order():
    queue = DedupQueue()
    queue.push(_frame(1))
    queue.push(_frame(2))

    assert queue.pop().observation_id == 1
    assert queue.pop().observation_id == 2
    assert queue.pop() is None
