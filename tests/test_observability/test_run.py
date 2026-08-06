from __future__ import annotations

from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import TelemetryMetric, TelemetryReading
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue
from leo_telemetry.observability.metrics import REGISTRY
from leo_telemetry.observability.run import _export_once


def _reading() -> TelemetryReading:
    return TelemetryReading(
        norad_id=31130,
        received_at=datetime.now(timezone.utc),
        metrics=(TelemetryMetric("battery_1_voltage", 4.1, "V"),),
    )


async def test_export_once_drains_reading_into_registry():
    queue = RedisTelemetryQueue(FakeAsyncRedis())
    await queue.push(_reading())

    exported = await _export_once(queue)

    assert exported is True
    assert await queue.qsize() == 0
    value = REGISTRY.get_sample_value(
        "leo_telemetry_metric",
        {
            "norad_id": "31130",
            "satellite": "CAPE-1",
            "name": "battery_1_voltage",
            "unit": "V",
        },
    )
    assert value == 4.1


async def test_export_once_on_empty_queue_is_a_noop():
    queue = RedisTelemetryQueue(FakeAsyncRedis())

    exported = await _export_once(queue)

    assert exported is False
