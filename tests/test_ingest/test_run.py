import httpx
from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import RawFrame
from leo_telemetry.ingest.audio_client import SatNOGSAudioClient
from leo_telemetry.ingest.client import SatNOGSClient
from leo_telemetry.ingest.redis_audio_queue import RedisAudioQueue
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue
from leo_telemetry.ingest.run import _audio_norad_ids_from_env, _norad_ids_from_env, _poll_audio_once, _poll_once


class FakeRawFrameStore:
    """Records insert_frame calls without touching a real database."""

    def __init__(self):
        self.inserted: list[RawFrame] = []

    async def insert_frame(self, frame: RawFrame) -> bool:
        self.inserted.append(frame)
        return True


def _telemetry_response(request: httpx.Request) -> httpx.Response:
    norad_id = int(request.url.params["satellite"])
    return httpx.Response(
        200,
        json={
            "results": [
                {
                    "observation_id": 1,
                    "norad_cat_id": norad_id,
                    "station_id": 42,
                    "timestamp": "2026-07-09T12:00:00Z",
                    "frame": b"\x7e\x00\x01\x7e".hex(),
                }
            ]
        },
    )


def test_norad_ids_from_env_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("NORAD_IDS", raising=False)

    from leo_telemetry.common.satellites import NORAD_IDS

    assert _norad_ids_from_env() == NORAD_IDS


def test_norad_ids_from_env_parses_csv(monkeypatch):
    monkeypatch.setenv("NORAD_IDS", "60525, 68458")

    assert _norad_ids_from_env() == (60525, 68458)


async def test_poll_once_pushes_new_frames_to_queue():
    transport = httpx.MockTransport(_telemetry_response)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)
    queue = RedisDedupQueue(FakeAsyncRedis())

    await _poll_once(client, queue)

    assert await queue.qsize() == 1
    await client.aclose()


async def test_poll_once_persists_new_frames_to_store():
    transport = httpx.MockTransport(_telemetry_response)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)
    queue = RedisDedupQueue(FakeAsyncRedis())
    store = FakeRawFrameStore()

    await _poll_once(client, queue, store)

    assert len(store.inserted) == 1
    await client.aclose()


async def test_poll_once_swallows_client_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)
    queue = RedisDedupQueue(FakeAsyncRedis())

    await _poll_once(client, queue)

    assert await queue.qsize() == 0
    await client.aclose()


def test_audio_norad_ids_from_env_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("AUDIO_NORAD_IDS", raising=False)

    from leo_telemetry.common.satellites import AUDIO_NORAD_IDS

    assert _audio_norad_ids_from_env() == AUDIO_NORAD_IDS


def test_audio_norad_ids_from_env_parses_csv(monkeypatch):
    monkeypatch.setenv("AUDIO_NORAD_IDS", "25544")

    assert _audio_norad_ids_from_env() == (25544,)


def _audio_observations_response(request: httpx.Request) -> httpx.Response:
    norad_id = int(request.url.params["norad_cat_id"])
    return httpx.Response(
        200,
        json=[
            {
                "id": 13494726,
                "norad_cat_id": norad_id,
                "ground_station": 42,
                "start": "2026-02-28T22:52:08Z",
                "payload": "https://network-satnogs.example/13494726.ogg",
            }
        ],
    )


async def test_poll_audio_once_pushes_new_observations_to_queue():
    transport = httpx.MockTransport(_audio_observations_response)
    client = SatNOGSAudioClient((25544,))
    client._client = httpx.AsyncClient(transport=transport)
    queue = RedisAudioQueue(FakeAsyncRedis())

    await _poll_audio_once(client, queue)

    assert await queue.qsize() == 1
    await client.aclose()


async def test_poll_audio_once_swallows_client_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    client = SatNOGSAudioClient((25544,))
    client._client = httpx.AsyncClient(transport=transport)
    queue = RedisAudioQueue(FakeAsyncRedis())

    await _poll_audio_once(client, queue)

    assert await queue.qsize() == 0
    await client.aclose()
