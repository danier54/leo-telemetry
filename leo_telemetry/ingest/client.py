"""SatNOGS telemetry polling client."""

from __future__ import annotations

from leo_telemetry.common.models import RawFrame


class SatNOGSClient:
    """Async polling client against the SatNOGS telemetry REST API.

    Queries are filtered by NORAD ID and must respect the API's rate limits.
    """

    def __init__(self, norad_ids: tuple[int, ...]):
        self.norad_ids = norad_ids

    async def poll(self) -> list[RawFrame]:
        """Fetch the latest telemetry frames for `self.norad_ids`."""
        raise NotImplementedError
