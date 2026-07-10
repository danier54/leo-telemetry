import httpx
from fakeredis import FakeAsyncRedis

from leo_telemetry.ingest.client import SatNOGSClient
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue
from leo_telemetry.ingest.run import _norad_ids_from_env, _poll_once


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
