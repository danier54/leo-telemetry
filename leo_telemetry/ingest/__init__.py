"""Data Ingest & Queue Management.

Polls the SatNOGS telemetry API for target NORAD IDs, handles rate limits,
and deduplicates overlapping captures before handing raw frames to decode.
"""
