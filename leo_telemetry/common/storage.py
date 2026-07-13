"""PostgreSQL-backed historical archive for raw telemetry frames.

This is the structured historical record described in the project plan: every
frame that passes ingest's Redis dedup check is also persisted here, so a
frame remains queryable and re-processable independent of the live FIFO
queue's consumer.

    ingest -> RedisDedupQueue (live FIFO, ephemeral)
           -> RawFrameStore   (Postgres, durable historical record)

Producer: ingest (writes via insert_frame)
Consumer: decode (reads via fetch_since, using a read-only role)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from leo_telemetry.common.models import RawFrame

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_frames (
    id BIGSERIAL PRIMARY KEY,
    norad_id INTEGER NOT NULL,
    observation_id BIGINT NOT NULL,
    observer_station_id BIGINT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    raw_bytes BYTEA NOT NULL,
    dedup_key TEXT NOT NULL UNIQUE,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS raw_frames_norad_id_received_at_idx
    ON raw_frames (norad_id, received_at);
"""


@dataclass(frozen=True)
class StoredFrame:
    """A RawFrame plus the database id assigned to it, for paging by id."""

    id: int
    frame: RawFrame


def _insert_params(frame: RawFrame) -> dict[str, Any]:
    return {
        "norad_id": frame.norad_id,
        "observation_id": frame.observation_id,
        "observer_station_id": frame.observer_station_id,
        "received_at": frame.received_at,
        "raw_bytes": frame.raw_bytes,
        "dedup_key": frame.dedup_key,
    }


def _row_to_raw_frame(row: dict[str, Any]) -> RawFrame:
    return RawFrame(
        norad_id=row["norad_id"],
        observation_id=row["observation_id"],
        observer_station_id=row["observer_station_id"],
        received_at=row["received_at"],
        raw_bytes=bytes(row["raw_bytes"]),
    )


class RawFrameStore:
    """Async wrapper around the single-table `raw_frames` Postgres archive."""

    def __init__(self, conn: psycopg.AsyncConnection):
        self._conn = conn

    @classmethod
    async def connect(cls, conninfo: str) -> "RawFrameStore":
        conn = await psycopg.AsyncConnection.connect(conninfo, autocommit=True)
        return cls(conn)

    async def ensure_schema(self) -> None:
        async with self._conn.cursor() as cur:
            await cur.execute(SCHEMA)

    async def insert_frame(self, frame: RawFrame) -> bool:
        """Insert a frame, ignoring it if its dedup_key is already present.

        Returns True if a new row was inserted.
        """
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO raw_frames
                    (norad_id, observation_id, observer_station_id,
                     received_at, raw_bytes, dedup_key)
                VALUES
                    (%(norad_id)s, %(observation_id)s, %(observer_station_id)s,
                     %(received_at)s, %(raw_bytes)s, %(dedup_key)s)
                ON CONFLICT (dedup_key) DO NOTHING
                """,
                _insert_params(frame),
            )
            return cur.rowcount > 0

    async def fetch_since(self, after_id: int = 0, limit: int = 500) -> list[StoredFrame]:
        """Return up to `limit` frames with id > after_id, oldest first.

        Intended for the decode track to page through the historical
        archive by id instead of re-scanning the whole table each time.
        """
        async with self._conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, norad_id, observation_id, observer_station_id,
                       received_at, raw_bytes
                FROM raw_frames
                WHERE id > %(after_id)s
                ORDER BY id ASC
                LIMIT %(limit)s
                """,
                {"after_id": after_id, "limit": limit},
            )
            rows = await cur.fetchall()
        return [StoredFrame(id=row["id"], frame=_row_to_raw_frame(row)) for row in rows]

    async def close(self) -> None:
        await self._conn.close()
