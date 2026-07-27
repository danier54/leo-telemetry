"""Telemetry Demultiplexing.

Maps validated payload bytes to explicit, typed physical measurements
using per-satellite byte specs (see `demux.specs`).
"""

from __future__ import annotations

from leo_telemetry.demux.demux import demultiplex

__all__ = ["demultiplex"]