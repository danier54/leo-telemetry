import httpx

from leo_telemetry.ingest.client import SatNOGSClient


def _telemetry_response(request: httpx.Request) -> httpx.Response:
    norad_id = int(request.url.params["satellite"])
    return httpx.Response(
        200,
        json={
            "next": None,
            "previous": None,
            "results": [
                {
                    "observation_id": 1,
                    "norad_cat_id": norad_id,
                    "station_id": 42,
                    "timestamp": "2026-07-09T12:00:00Z",
                    "frame": b"\x7e\x00\x01\x7e".hex(),
                }
            ],
        },
    )


async def test_poll_maps_response_to_raw_frames():
    transport = httpx.MockTransport(_telemetry_response)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)

    frames = await client.poll()

    assert len(frames) == 1
    assert frames[0].norad_id == 60525
    assert frames[0].observation_id == 1
    assert frames[0].observer_station_id == 42
    assert frames[0].raw_bytes == b"\x7e\x00\x01\x7e"

    await client.aclose()


async def test_poll_defaults_missing_observation_and_station_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "observation_id": None,
                        "station_id": None,
                        "timestamp": "2026-07-09T12:00:00Z",
                        "frame": "",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)

    frames = await client.poll()

    assert frames[0].observation_id == -1
    assert frames[0].observer_station_id == 0
    assert frames[0].raw_bytes == b""

    await client.aclose()


async def test_poll_retries_once_after_429():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return _telemetry_response(request)

    transport = httpx.MockTransport(handler)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)

    frames = await client.poll()

    assert calls["count"] == 2
    assert len(frames) == 1

    await client.aclose()
