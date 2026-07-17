import httpx

from leo_telemetry.ingest.audio_client import SatNOGSAudioClient


def _observations_response(request: httpx.Request) -> httpx.Response:
    assert request.url.params["status"] == "good"
    norad_id = int(request.url.params["norad_cat_id"])
    return httpx.Response(
        200,
        json=[
            {
                "id": 13494726,
                "norad_cat_id": norad_id,
                "ground_station": 42,
                "start": "2026-02-28T22:52:08Z",
                "payload": "https://network-satnogs.example/satnogs_13494726.ogg",
            },
            {
                "id": 13494727,
                "norad_cat_id": norad_id,
                "ground_station": 42,
                "start": "2026-02-28T22:53:08Z",
                "payload": None,
            },
        ],
    )


async def test_poll_maps_response_to_audio_observations_with_payload_only():
    transport = httpx.MockTransport(_observations_response)
    client = SatNOGSAudioClient((25544,))
    client._client = httpx.AsyncClient(transport=transport)

    observations = await client.poll()

    assert len(observations) == 1
    assert observations[0].norad_id == 25544
    assert observations[0].observation_id == 13494726
    assert observations[0].station_id == 42
    assert observations[0].payload_url == "https://network-satnogs.example/satnogs_13494726.ogg"

    await client.aclose()
