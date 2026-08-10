from __future__ import annotations

import pytest
from datetime import datetime, timezone
from dataclasses import replace
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
    """Ensure the DLQ respects its maximum size configuration and evicts oldest."""
    client = FakeAsyncRedis()
    dlq = DemuxDeadLetterQueue(client, max_size=2)
    
    # Create three distinct failures with realistic error reasons  to prove FIFO eviction
    frame_1 = replace(mock_decoded_frame, norad_id=1)
    fail_1 = FailedDemuxFrame.from_exception(frame_1, ValueError("Truncated payload: expected 15 bytes"))
    
    frame_2 = replace(mock_decoded_frame, norad_id=2)
    fail_2 = FailedDemuxFrame.from_exception(frame_2, ValueError("Invalid APID: 105"))
    
    frame_3 = replace(mock_decoded_frame, norad_id=3)
    fail_3 = FailedDemuxFrame.from_exception(frame_3, ValueError("Unrecognized packet type"))
    
    await dlq.push(fail_1)
    await dlq.push(fail_2)
    await dlq.push(fail_3)  # Should evict fail_1
    
    assert await dlq.qsize() == 2
    
    # Verify fail_1 is gone, and fail_2 and fail_3 remain in order
    recent = await dlq.get_recent(count=2)
    assert recent[0].norad_id == 2
    assert recent[1].norad_id == 3


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