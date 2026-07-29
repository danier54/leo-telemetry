from __future__ import annotations

from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import TelemetryMetric, TelemetryReading
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue


def _reading(norad_id: int, value: float = 1.0) -> TelemetryReading:
    return TelemetryReading(
        norad_id=norad_id,
        received_at=datetime.now(timezone.utc),
        metrics=(TelemetryMetric(name="test_metric", value=value, unit="V"),),
    )


async def test_push_always_succeeds_no_dedup():
    queue = RedisTelemetryQueue(FakeAsyncRedis())

    await queue.push(_reading(60525))
    await queue.push(_reading(60525))

    assert await queue.qsize() == 2


async def test_pop_returns_readings_in_fifo_order():
    queue = RedisTelemetryQueue(FakeAsyncRedis())
    await queue.push(_reading(60525))
    await queue.push(_reading(68458))

    first = await queue.pop()
    second = await queue.pop()

    assert first is not None
    assert second is not None

    assert first.norad_id == 60525
    assert second.norad_id == 68458
    assert await queue.pop() is None


async def test_qsize_reflects_pending_items():
    queue = RedisTelemetryQueue(FakeAsyncRedis())
    assert await queue.qsize() == 0

    await queue.push(_reading(60525))
    assert await queue.qsize() == 1


async def test_queue_boundary_eviction():
    queue = RedisTelemetryQueue(FakeAsyncRedis(), max_queue_size=2)

    await queue.push(_reading(60525, value=10.0))
    await queue.push(_reading(68458, value=20.0))
    await queue.push(_reading(31130, value=30.0))

    assert await queue.qsize() == 2

    # The first item (60525) should be evicted by tail-drop ltrim
    first = await queue.pop()
    second = await queue.pop()

    assert first is not None
    assert second is not None

    assert first.norad_id == 68458
    assert first.metrics[0].value == 20.0
    assert second.norad_id == 31130
    assert second.metrics[0].value == 30.0

    assert await queue.pop() is None