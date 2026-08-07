from __future__ import annotations

import pytest
from datetime import datetime, timezone
from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import DecodedFrame
from leo_telemetry.demux.dlq import DemuxDeadLetterQueue, FailedDemuxFrame


@pytest.fixture
def mock_decoded_frame() -> DecodedFrame:
    return DecodedFrame(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=b"\x00\xFF",
        crc_valid=True,
    )


@pytest.mark.asyncio
async def test_dlq_from_exception_captures_context(mock_decoded_frame):
    """Extract the stack trace and hex payload."""
    try:
        raise ValueError("Buffer overflow: required 216 bytes, got 2")
    except ValueError as exc:
        failure = FailedDemuxFrame.from_exception(mock_decoded_frame, exc)
        
    assert failure.norad_id == 60525
    assert failure.payload_hex == "00ff"
    assert "Buffer overflow" in failure.error_message
    assert "Traceback" in failure.traceback


@pytest.mark.asyncio
async def test_dlq_pushes_with_boundary_eviction(mock_decoded_frame):
    """Ensure the DLQ respects its maximum size configuration."""
    client = FakeAsyncRedis()
    dlq = DemuxDeadLetterQueue(client, max_size=2)
    
    failure = FailedDemuxFrame.from_exception(mock_decoded_frame, ValueError("Test"))
    
    await dlq.push(failure)
    await dlq.push(failure)
    await dlq.push(failure)  # Should evict the first item
    
    assert await dlq.qsize() == 2


@pytest.mark.asyncio
async def test_dlq_get_recent_reads_without_popping(mock_decoded_frame):
    """Ensure lrange retrieves items without draining the queue."""
    client = FakeAsyncRedis()
    dlq = DemuxDeadLetterQueue(client, max_size=10)
    
    failure = FailedDemuxFrame.from_exception(mock_decoded_frame, ValueError("Test"))
    await dlq.push(failure)
    
    results = await dlq.get_recent(count=5)
    
    assert len(results) == 1
    assert results[0].norad_id == 60525
    
    # Queue size should remain unchanged
    assert await dlq.qsize() == 1