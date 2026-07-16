from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.ingest.audio_client import AudioObservation
from leo_telemetry.ingest.redis_audio_queue import RedisAudioQueue


def _observation(observation_id: int) -> AudioObservation:
    return AudioObservation(
        norad_id=25544,
        observation_id=observation_id,
        station_id=42,
        observed_at=datetime.now(timezone.utc),
        payload_url=f"https://network-satnogs.example/{observation_id}.ogg",
    )


async def test_push_accepts_first_occurrence():
    queue = RedisAudioQueue(FakeAsyncRedis())

    assert await queue.push(_observation(1)) is True
    assert await queue.qsize() == 1


async def test_push_rejects_duplicate():
    queue = RedisAudioQueue(FakeAsyncRedis())
    await queue.push(_observation(1))

    assert await queue.push(_observation(1)) is False
    assert await queue.qsize() == 1


async def test_pop_returns_observations_in_fifo_order():
    queue = RedisAudioQueue(FakeAsyncRedis())
    await queue.push(_observation(1))
    await queue.push(_observation(2))

    first = await queue.pop()
    second = await queue.pop()

    assert first.observation_id == 1
    assert second.observation_id == 2
    assert await queue.pop() is None
