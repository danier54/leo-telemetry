from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import RawFrame
from leo_telemetry.ingest.redis_dedup import SEEN_KEY, RedisDedupQueue


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


async def test_queue_is_trimmed_to_max_size_dropping_oldest_first():
    queue = RedisDedupQueue(FakeAsyncRedis(), max_queue_size=2)

    await queue.push(_frame(1))
    await queue.push(_frame(2))
    await queue.push(_frame(3))

    assert await queue.qsize() == 2
    assert (await queue.pop()).observation_id == 2
    assert (await queue.pop()).observation_id == 3


async def test_peek_all_returns_queued_frames_without_removing_them():
    queue = RedisDedupQueue(FakeAsyncRedis())
    await queue.push(_frame(1))
    await queue.push(_frame(2))

    peeked = await queue.peek_all()

    assert [frame.observation_id for frame in peeked] == [1, 2]
    assert await queue.qsize() == 2


async def test_seen_ttl_is_set_once_and_not_refreshed_on_later_pushes():
    redis_client = FakeAsyncRedis()
    queue = RedisDedupQueue(redis_client, seen_ttl_seconds=1000)

    await queue.push(_frame(1))
    ttl_after_first_push = await redis_client.ttl(SEEN_KEY)

    await queue.push(_frame(2))
    ttl_after_second_push = await redis_client.ttl(SEEN_KEY)

    assert ttl_after_first_push == 1000
    assert ttl_after_second_push == ttl_after_first_push
