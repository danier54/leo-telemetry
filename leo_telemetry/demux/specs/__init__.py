"""Per-satellite byte layout specs, one module per NORAD ID/mission.

Each spec module should expose a function that takes a `bytes` payload and
returns a tuple of `TelemetryMetric` for that satellite's known telemetry
fields (battery voltage, CPU uptime, temperature, etc.), based on the
hardware documentation published by the satellite's maintainer.
"""
