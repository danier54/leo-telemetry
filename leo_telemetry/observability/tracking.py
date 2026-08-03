"""Skyfield-based orbital position tracking."""

from __future__ import annotations

from skyfield.api import EarthSatellite, load, wgs84


def propagate_position(norad_id: int, tle: tuple[str, str]) -> tuple[float, float, float]:
    """Compute current (lat, lon, alt_km) for a satellite from its TLE lines."""
    if len(tle) != 2:
        raise ValueError("TLE input must contain exactly two line elements.")

    line1, line2 = tle
    if not line1 or not line2:
        raise ValueError("TLE lines must not be empty.")

    ts = load.timescale()
    eph = load("de421.bsp")
    satellite = EarthSatellite(line1, line2, name=str(norad_id), epoch=ts.now())
    position = satellite.at(ts.now())
    geodetic = wgs84.geographic_position_of(position)

    return (
        float(geodetic.latitude.degrees),
        float(geodetic.longitude.degrees),
        float(geodetic.elevation.km),
    )
