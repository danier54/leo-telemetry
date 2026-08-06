"""Skyfield-based orbital position tracking."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import httpx
from skyfield.api import EarthSatellite, load, wgs84

from leo_telemetry.observability.metrics import (
    SATELLITE_ALTITUDE,
    SATELLITE_LATITUDE,
    SATELLITE_LONGITUDE,
    SATELLITE_VELOCITY,
    satellite_label,
)

logger = logging.getLogger(__name__)

CELESTRAK_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php"

# Module-level timescale: uses Skyfield's builtin data files, so no
# network or disk downloads are needed at import or call time.
_TIMESCALE = load.timescale()


def propagate_state(
    norad_id: int,
    tle: tuple[str, str],
    at: datetime | None = None,
) -> tuple[float, float, float, float]:
    """Compute current (lat, lon, alt_km, speed_km_s) for a satellite.

    Args:
        norad_id: Satellite catalog number, used only for labeling.
        tle:      The two TLE element lines.
        at:       Optional UTC instant to propagate to; defaults to now.
                  Naive datetimes are treated as UTC, not local time.
    """
    satellite = EarthSatellite(tle[0], tle[1], str(norad_id), _TIMESCALE)
    if at is not None:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        t = _TIMESCALE.from_datetime(at.astimezone(timezone.utc))
    else:
        t = _TIMESCALE.now()
    geocentric = satellite.at(t)
    subpoint = wgs84.geographic_position_of(geocentric)
    speed_km_s = math.hypot(*geocentric.velocity.km_per_s)
    return (
        subpoint.latitude.degrees,
        subpoint.longitude.degrees,
        subpoint.elevation.km,
        speed_km_s,
    )


def propagate_position(
    norad_id: int,
    tle: tuple[str, str],
    at: datetime | None = None,
) -> tuple[float, float, float]:
    """Compute current (lat, lon, alt_km) for a satellite from its TLE lines."""
    lat, lon, alt_km, _speed = propagate_state(norad_id, tle, at)
    return (lat, lon, alt_km)


async def fetch_tle(norad_id: int, client: httpx.AsyncClient) -> tuple[str, str] | None:
    """Fetch the latest TLE for a satellite from Celestrak.

    Returns:
        The two element lines, or None when Celestrak has no elements for
        the id (e.g. not yet cataloged) or the request fails -- tracking
        is best-effort and must never take the exporter down.
    """
    try:
        response = await client.get(
            CELESTRAK_TLE_URL,
            params={"CATNR": str(norad_id), "FORMAT": "TLE"},
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("TLE fetch failed for norad=%s: %s", norad_id, exc)
        return None

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    element_lines = [ln for ln in lines if ln[:2] in ("1 ", "2 ")]
    if len(element_lines) < 2:
        logger.warning(
            "Celestrak returned no usable TLE for norad=%s: %r",
            norad_id,
            response.text[:80],
        )
        return None
    return (element_lines[0], element_lines[1])


def update_position_metrics(norad_id: int, tle: tuple[str, str]) -> None:
    """Propagate one satellite and publish its orbital state to the registry."""
    lat, lon, alt_km, speed_km_s = propagate_state(norad_id, tle)
    labels = {"norad_id": str(norad_id), "satellite": satellite_label(norad_id)}
    SATELLITE_LATITUDE.labels(**labels).set(lat)
    SATELLITE_LONGITUDE.labels(**labels).set(lon)
    SATELLITE_ALTITUDE.labels(**labels).set(alt_km)
    SATELLITE_VELOCITY.labels(**labels).set(speed_km_s)
