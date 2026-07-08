"""Target CubeSats for the initial pipeline scope."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SatelliteConfig:
    name: str
    norad_id: int
    maintainer: str
    protocol: str


TARGET_SATELLITES: tuple[SatelliteConfig, ...] = (
    SatelliteConfig(
        name="ORESAT0.5",
        norad_id=60525,
        maintainer="Portland State Aerospace Society",
        protocol="9600bps FSK AX.25",
    ),
    SatelliteConfig(
        name="SAL-E/CP16",
        norad_id=68458,
        maintainer="California Polytechnic State University",
        protocol="9600bps FSK AX.25",
    ),
    SatelliteConfig(
        name="CAPE-1",
        norad_id=31130,
        maintainer="University of Louisiana",
        protocol="9600bps FSK AX.25",
    ),
)

NORAD_IDS: tuple[int, ...] = tuple(sat.norad_id for sat in TARGET_SATELLITES)
