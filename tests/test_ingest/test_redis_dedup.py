from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import RawFrame
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue


def _frame(observation_id: int) -> RawFrame:
    return RawFrame(
        norad_id=60525,
        observation_id=observation_id,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
        raw_bytes=b"\x7e\x00\x01\x7e",
    )


async def test_push_accepts_first_occurrence():
    queue = RedisDedupQueue(FakeAsyncRedis())

    assert await queue.push(_frame(1)) is True
    assert await queue.qsize() == 1


async def test_push_rejects_duplicate():
    queue = RedisDedupQueue(FakeAsyncRedis())
    await queue.push(_frame(1))

    assert await queue.push(_frame(1)) is False
    assert await queue.qsize() == 1


async def test_pop_returns_frames_in_fifo_order():
    queue = RedisDedupQueue(FakeAsyncRedis())
    await queue.push(_frame(1))
    await queue.push(_frame(2))

    first = await queue.pop()
    second = await queue.pop()

    assert first.observation_id == 1
    assert second.observation_id == 2
    assert await queue.pop() is None
