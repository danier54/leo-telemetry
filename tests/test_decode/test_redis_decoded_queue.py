from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import DecodedFrame
from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue


def _frame(norad_id: int) -> DecodedFrame:
    return DecodedFrame(
        norad_id=norad_id,
        received_at=datetime.now(timezone.utc),
        src_callsign="KK6ABC",
        dest_callsign="APRS",
        payload=b"\x01\x02\x03",
        crc_valid=True,
    )


async def test_push_always_succeeds_no_dedup():
    queue = RedisDecodedQueue(FakeAsyncRedis())

    await queue.push(_frame(60525))
    await queue.push(_frame(60525))  # identical content, still not deduped

    assert await queue.qsize() == 2


async def test_pop_returns_frames_in_fifo_order():
    queue = RedisDecodedQueue(FakeAsyncRedis())
    await queue.push(_frame(60525))
    await queue.push(_frame(68458))

    first = await queue.pop()
    second = await queue.pop()

    assert first.norad_id == 60525
    assert second.norad_id == 68458
    assert await queue.pop() is None


async def test_qsize_reflects_pending_items():
    queue = RedisDecodedQueue(FakeAsyncRedis())
    assert await queue.qsize() == 0

    await queue.push(_frame(60525))
    assert await queue.qsize() == 1
