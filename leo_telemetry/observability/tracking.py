"""Skyfield-based orbital position tracking."""

from __future__ import annotations


def propagate_position(norad_id: int, tle: tuple[str, str]) -> tuple[float, float, float]:
    """Compute current (lat, lon, alt_km) for a satellite from its TLE lines."""
    raise NotImplementedError
