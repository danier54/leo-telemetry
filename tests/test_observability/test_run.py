from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import TelemetryMetric, TelemetryReading
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue
from leo_telemetry.ingest.redis_audio_queue import QUEUE_KEY as AUDIO_QUEUE_KEY
from leo_telemetry.observability import run as run_module
from leo_telemetry.observability.last_readings import LastReadingStore
from leo_telemetry.observability.metrics import REGISTRY
from leo_telemetry.observability.run import (
    ObservabilityConfig,
    _export_once,
    _replay_persisted_readings,
    _track_positions,
    _update_queue_depths,
)


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


async def test_export_once_persists_reading_for_replay():
    redis_client = FakeAsyncRedis()
    queue = RedisTelemetryQueue(redis_client)
    store = LastReadingStore(redis_client)
    await queue.push(_reading())

    await _export_once(queue, store)

    stored = await store.load_all()
    assert len(stored) == 1
    assert stored[0].norad_id == 31130


async def test_store_keeps_newer_reading_over_stale_save():
    redis_client = FakeAsyncRedis()
    store = LastReadingStore(redis_client)
    newer = TelemetryReading(
        norad_id=31130,
        received_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        metrics=(TelemetryMetric("battery_1_voltage", 4.2, "V"),),
    )
    older = TelemetryReading(
        norad_id=31130,
        received_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        metrics=(TelemetryMetric("battery_1_voltage", 1.0, "V"),),
    )

    await store.save(newer)
    await store.save(older)

    stored = await store.load_all()
    assert len(stored) == 1
    assert stored[0].received_at == newer.received_at


async def test_replay_restores_gauges_without_counting_readings():
    redis_client = FakeAsyncRedis()
    store = LastReadingStore(redis_client)
    await store.save(_reading())
    labels = {"norad_id": "31130", "satellite": "CAPE-1"}
    count_before = (
        REGISTRY.get_sample_value(
            "leo_telemetry_readings_total", labels
        ) or 0.0
    )

    await _replay_persisted_readings(store)

    value = REGISTRY.get_sample_value(
        "leo_telemetry_metric",
        {**labels, "name": "battery_1_voltage", "unit": "V"},
    )
    assert value == 4.1
    count_after = REGISTRY.get_sample_value(
        "leo_telemetry_readings_total", labels
    )
    assert count_after == count_before  # replay must not inflate throughput


async def test_update_queue_depths_reports_every_stage():
    redis_client = FakeAsyncRedis()
    queue = RedisTelemetryQueue(redis_client)
    await queue.push(_reading())
    await redis_client.rpush(AUDIO_QUEUE_KEY, b"queued audio observation")

    await _update_queue_depths(redis_client)

    expected_depths = (
        ("raw", 0.0),
        ("audio", 1.0),
        ("decoded", 0.0),
        ("telemetry", 1.0),
    )
    for queue_name, expected in expected_depths:
        depth = REGISTRY.get_sample_value(
            "leo_telemetry_queue_depth", {"queue": queue_name}
        )
        assert depth == expected


async def test_track_positions_survives_propagation_errors(monkeypatch):
    config = ObservabilityConfig(
        redis_url="redis://unused",
        poll_interval_seconds=0.01,
        metrics_port=0,
        tle_refresh_seconds=1000.0,
        position_update_seconds=0.01,
        log_level="INFO",
    )
    update_calls: list[int] = []

    async def fake_fetch_tle(norad_id, client):
        return ("1 fake", "2 fake")

    def always_fails(norad_id, tle):
        update_calls.append(norad_id)
        raise RuntimeError("malformed TLE")

    monkeypatch.setattr(run_module, "fetch_tle", fake_fetch_tle)
    monkeypatch.setattr(run_module, "update_position_metrics", always_fails)

    stop_event = asyncio.Event()
    tracker = asyncio.create_task(_track_positions(config, stop_event))
    await asyncio.sleep(0.1)

    assert not tracker.done()  # failures were contained, loop kept running
    assert len(update_calls) > 3  # more than one full pass over the satellites

    stop_event.set()
    await tracker
