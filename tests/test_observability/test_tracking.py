from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from leo_telemetry.observability.metrics import REGISTRY
from leo_telemetry.observability.tracking import (
    fetch_tle,
    propagate_position,
    update_position_metrics,
)

# Historical ISS TLE; propagation from it is deterministic and offline.
ISS_TLE = (
    "1 25544U 98067A   24001.50000000  .00016717  00000-0  30777-3 0  9992",
    "2 25544  51.6400 208.9163 0006317  69.9862 290.2260 15.49560532430000",
)
EPOCH = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_propagate_position_matches_known_iss_subpoint():
    lat, lon, alt_km = propagate_position(25544, ISS_TLE, at=EPOCH)

    assert lat == pytest.approx(0.0358, abs=0.01)
    assert lon == pytest.approx(-71.701, abs=0.01)
    assert alt_km == pytest.approx(417.27, abs=0.5)


def test_propagate_position_stays_in_leo_bounds():
    lat, lon, alt_km = propagate_position(25544, ISS_TLE, at=EPOCH)

    assert -90.0 <= lat <= 90.0
    assert -180.0 <= lon <= 180.0
    assert 150.0 < alt_km < 2000.0


def test_update_position_metrics_publishes_subpoint_gauges():
    update_position_metrics(25544, ISS_TLE)

    labels = {"norad_id": "25544", "satellite": "25544"}
    lat = REGISTRY.get_sample_value(
        "leo_telemetry_satellite_latitude_degrees", labels
    )
    lon = REGISTRY.get_sample_value(
        "leo_telemetry_satellite_longitude_degrees", labels
    )
    alt = REGISTRY.get_sample_value(
        "leo_telemetry_satellite_altitude_kilometers", labels
    )
    assert lat is not None and -90.0 <= lat <= 90.0
    assert lon is not None and -180.0 <= lon <= 180.0
    assert alt is not None and alt > 150.0


def _client_returning(body: str, status_code: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_fetch_tle_parses_celestrak_response():
    body = f"ISS (ZARYA)\r\n{ISS_TLE[0]}\r\n{ISS_TLE[1]}\r\n"
    async with _client_returning(body) as client:
        tle = await fetch_tle(25544, client)

    assert tle == ISS_TLE


async def test_fetch_tle_returns_none_when_satellite_not_cataloged():
    async with _client_returning("No GP data found") as client:
        tle = await fetch_tle(68458, client)

    assert tle is None


async def test_fetch_tle_returns_none_on_http_error():
    async with _client_returning("upstream broke", status_code=502) as client:
        tle = await fetch_tle(25544, client)

    assert tle is None
