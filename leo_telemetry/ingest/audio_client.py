"""SatNOGS Network polling client for raw off-air audio observations.

Distinct from SatNOGSClient (client.py), which polls SatNOGS DB's
already-decoded telemetry API: this hits SatNOGS Network's observations
endpoint instead, which carries real audio recordings pre-demodulation. Used
for the AFSK1200 demod stretch work (leo_telemetry/decode/afsk1200.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import httpx

SATNOGS_NETWORK_OBSERVATIONS_URL = "https://network.satnogs.org/api/observations/"


@dataclass(frozen=True)
class AudioObservation:
    """A SatNOGS Network observation carrying a real off-air audio recording.

    `payload_url` points at the recording itself -- only the metadata is
    queued, since audio files run into the megabytes and decode can fetch
    the URL directly when it's ready to process one.
    """

    norad_id: int
    observation_id: int
    station_id: int
    observed_at: datetime
    payload_url: str

    @property
    def dedup_key(self) -> str:
        return f"{self.norad_id}:{self.observation_id}"


class SatNOGSAudioClient:
    """Polls SatNOGS Network for new audio observations of a satellite."""

    def __init__(
        self,
        norad_ids: tuple[int, ...],
        *,
        base_url: str = SATNOGS_NETWORK_OBSERVATIONS_URL,
        page_size: int = 25,
        timeout_seconds: float = 30.0,
    ):
        self.norad_ids = norad_ids
        self.base_url = base_url
        self.page_size = page_size
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def poll(self) -> list[AudioObservation]:
        """Fetch the latest audio-bearing observations for every configured NORAD ID."""
        observations: list[AudioObservation] = []
        for norad_id in self.norad_ids:
            observations.extend(await self._poll_one(norad_id))
        return observations

    async def _poll_one(self, norad_id: int) -> list[AudioObservation]:
        params = {"norad_cat_id": norad_id, "format": "json", "page_size": self.page_size}
        response = await self._client.get(self.base_url, params=params)
        response.raise_for_status()
        results = response.json() or []
        return [
            self._to_audio_observation(norad_id, entry)
            for entry in results
            if entry.get("payload")
        ]

    @staticmethod
    def _to_audio_observation(norad_id: int, entry: dict) -> AudioObservation:
        timestamp = entry["start"].replace("Z", "+00:00")
        return AudioObservation(
            norad_id=norad_id,
            observation_id=entry["id"],
            station_id=entry.get("ground_station") or 0,
            observed_at=datetime.fromisoformat(timestamp),
            payload_url=entry["payload"],
        )
