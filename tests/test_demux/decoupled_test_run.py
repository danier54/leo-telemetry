from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import DecodedFrame
from leo_telemetry.demux.redis_telemetry_queue import RedisTelemetryQueue
from leo_telemetry.demux.run import _demux_once


class FakeDecodedInputQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[DecodedFrame] = asyncio.Queue()

    async def push(self, frame: DecodedFrame) -> None:
        await self._queue.put(frame)

    async def pop(self) -> DecodedFrame | None:
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None


def _valid_decoded_frame() -> DecodedFrame:
    payload = bytearray(216)
    payload[49:51] = b"\x08\x20"  # battery 1 pack 1 vbatt: 8200 mV little-endian
    return DecodedFrame(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=bytes(payload),
        crc_valid=True,
    )


def _malformed_decoded_frame() -> DecodedFrame:
    return DecodedFrame(
        norad_id=60525,
        received_at=datetime.now(timezone.utc),
        src_callsign="KJ7SAT",
        dest_callsign="SPACE",
        payload=b"\x00" * 3,  # shorter than ORESAT's required 216-byte struct
        crc_valid=True,
    )


async def test_demux_once_pushes_valid_frame_to_output_queue():
    redis_client = FakeAsyncRedis()
    in_queue = FakeDecodedInputQueue()
    out_queue = RedisTelemetryQueue(redis_client)
    await in_queue.push(_valid_decoded_frame())

    processed = await _demux_once(in_queue, out_queue)

    assert processed is True
    assert await out_queue.qsize() == 1
    result = await out_queue.pop()
    
    assert result is not None
    assert result.norad_id == 60525
    assert len(result.metrics) > 0
    vbatt = next(m for m in result.metrics if m.name == "battery_1_pack_1_vbatt")
    assert vbatt.value == 8200.0
    assert vbatt.unit == "mV"


async def test_demux_once_drops_malformed_frame_without_crashing():
    redis_client = FakeAsyncRedis()
    in_queue = FakeDecodedInputQueue()
    out_queue = RedisTelemetryQueue(redis_client)
    await in_queue.push(_malformed_decoded_frame())

    processed = await _demux_once(in_queue, out_queue)

    assert processed is True
    assert await out_queue.qsize() == 0


async def test_demux_once_on_empty_queue_is_a_noop():
    redis_client = FakeAsyncRedis()
    in_queue = FakeDecodedInputQueue()
    out_queue = RedisTelemetryQueue(redis_client)

    processed = await _demux_once(in_queue, out_queue)

    assert processed is False
    assert await out_queue.qsize() == 0