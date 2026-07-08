"""Deduplication queue for overlapping ground-station captures."""

from __future__ import annotations

from collections import deque

from leo_telemetry.common.models import RawFrame


class DedupQueue:
    """FIFO queue that drops frames already seen via `RawFrame.dedup_key`.

    This in-memory implementation is a placeholder for the eventual
    Redis-backed dedup registry described in the design doc.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._queue: deque[RawFrame] = deque()

    def push(self, frame: RawFrame) -> bool:
        """Add a frame if unseen. Returns True if it was added."""
        if frame.dedup_key in self._seen:
            return False
        self._seen.add(frame.dedup_key)
        self._queue.append(frame)
        return True

    def pop(self) -> RawFrame | None:
        """Remove and return the oldest queued frame, or None if empty."""
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)
