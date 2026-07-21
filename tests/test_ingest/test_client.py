import httpx

from leo_telemetry.ingest.client import (
    DEFAULT_RETRY_AFTER_SECONDS,
    MAX_RETRY_AFTER_SECONDS,
    SatNOGSClient,
)


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


async def test_poll_skips_corrupted_entries_keeps_good_ones():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"observation_id": 1, "station_id": 1, "timestamp": "2026-07-09T12:00:00Z", "frame": "zzzz-not-hex"},
                    {"observation_id": 2, "station_id": 1, "timestamp": "2026-07-09T12:01:00Z", "frame": "7e0"},
                    {"observation_id": 3, "station_id": 1, "frame": "7e00017e"},
                    {"observation_id": 4, "station_id": 1, "timestamp": "not a timestamp", "frame": "7e00017e"},
                    {"observation_id": 5, "station_id": 1, "timestamp": "2026-07-09T12:02:00Z", "frame": "7e00017e"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)

    frames = await client.poll()

    assert [frame.observation_id for frame in frames] == [5]

    await client.aclose()


async def test_poll_raises_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated timeout")

    transport = httpx.MockTransport(handler)
    client = SatNOGSClient((60525,), min_interval_seconds=0)
    client._client = httpx.AsyncClient(transport=transport)

    try:
        await client.poll()
        raised = False
    except httpx.TimeoutException:
        raised = True

    assert raised, "timeouts must propagate so the poll loop can log and retry next cycle"
    await client.aclose()


def test_parse_retry_after_defends_against_bad_headers():
    assert SatNOGSClient._parse_retry_after("10") == 10.0
    assert SatNOGSClient._parse_retry_after(None) == DEFAULT_RETRY_AFTER_SECONDS
    assert SatNOGSClient._parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") == DEFAULT_RETRY_AFTER_SECONDS
    assert SatNOGSClient._parse_retry_after("-5") == DEFAULT_RETRY_AFTER_SECONDS
    assert SatNOGSClient._parse_retry_after("999999") == MAX_RETRY_AFTER_SECONDS


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
