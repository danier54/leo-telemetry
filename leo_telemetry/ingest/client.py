"""SatNOGS telemetry polling client."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime

import httpx

from leo_telemetry.common.models import RawFrame

logger = logging.getLogger(__name__)

SATNOGS_TELEMETRY_URL = "https://db.satnogs.org/api/telemetry/"


class RateLimiter:
    """Enforces a minimum interval between requests made through it."""

    def __init__(self, min_interval_seconds: float):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_at: float | None = None

    async def wait(self) -> None:
        loop = asyncio.get_event_loop()
        if self._last_request_at is not None:
            remaining = self.min_interval_seconds - (loop.time() - self._last_request_at)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request_at = loop.time()


class SatNOGSClient:
    """Async polling client against the SatNOGS DB telemetry REST API.

    Queries are filtered by NORAD ID and paced by `min_interval_seconds`
    between requests to stay within SatNOGS' public rate limits. A 429
    response is retried once after honoring the server's `Retry-After`
    header.
    """

    def __init__(
        self,
        norad_ids: tuple[int, ...],
        *,
        base_url: str = SATNOGS_TELEMETRY_URL,
        api_token: str | None = None,
        min_interval_seconds: float = 5.0,
        page_size: int = 50,
        timeout_seconds: float = 30.0,
    ):
        self.norad_ids = norad_ids
        self.base_url = base_url
        self.api_token = api_token
        self.page_size = page_size
        self._limiter = RateLimiter(min_interval_seconds)
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def poll(self) -> list[RawFrame]:
        """Fetch the latest telemetry frames for every configured NORAD ID."""
        frames: list[RawFrame] = []
        for norad_id in self.norad_ids:
            frames.extend(await self._poll_one(norad_id))
        return frames

    async def _poll_one(self, norad_id: int) -> list[RawFrame]:
        await self._limiter.wait()
        headers = {"Authorization": f"Token {self.api_token}"} if self.api_token else {}
        params = {"norad_cat_id": norad_id, "format": "json", "page_size": self.page_size}

        response = await self._client.get(self.base_url, params=params, headers=headers)

        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 30))
            logger.warning("Rate limited by SatNOGS for NORAD %s, backing off %ss", norad_id, retry_after)
            await asyncio.sleep(retry_after)
            response = await self._client.get(self.base_url, params=params, headers=headers)

        response.raise_for_status()
        return [self._to_raw_frame(norad_id, entry) for entry in response.json()]

    @staticmethod
    def _to_raw_frame(norad_id: int, entry: dict) -> RawFrame:
        frame_b64 = entry.get("frame") or ""
        timestamp = entry["timestamp"].replace("Z", "+00:00")
        return RawFrame(
            norad_id=norad_id,
            observation_id=entry["id"],
            observer_station_id=entry.get("station") or 0,
            received_at=datetime.fromisoformat(timestamp),
            raw_bytes=base64.b64decode(frame_b64) if frame_b64 else b"",
        )
