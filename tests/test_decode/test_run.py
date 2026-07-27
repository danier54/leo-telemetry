from fakeredis import FakeAsyncRedis

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue
from leo_telemetry.decode.run import _decode_once
from leo_telemetry.ingest.redis_dedup import RedisDedupQueue
from tests.test_decode.test_ax25 import _build_ax25_frame, _shifted_address
from datetime import datetime, timezone


def _valid_raw_frame(observation_id: int = 1) -> RawFrame:
    dest = _shifted_address("CQ", 0, last=False)
    src = _shifted_address("KJ6ABC", 0, last=True)
    frame_bytes = _build_ax25_frame(
        addresses=[dest, src], control_pid=b"\x03\xf0", info=b"hello", append_fcs=False
    )
    return RawFrame(
        norad_id=60525,
        observation_id=observation_id,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
        raw_bytes=frame_bytes,
    )


def _malformed_raw_frame() -> RawFrame:
    return RawFrame(
        norad_id=60525,
        observation_id=2,
        observer_station_id=42,
        received_at=datetime.now(timezone.utc),
        raw_bytes=b"\x00" * 3,  # shorter than the 15-byte minimum decode_frame requires
    )


async def test_decode_once_pushes_valid_frame_to_output_queue():
    in_queue = RedisDedupQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())
    await in_queue.push(_valid_raw_frame())

    decoded = await _decode_once(in_queue, out_queue)

    assert decoded is True
    assert await out_queue.qsize() == 1
    result = await out_queue.pop()
    assert result.norad_id == 60525
    assert result.src_callsign == "KJ6ABC"
    assert result.payload == b"hello"


async def test_decode_once_drops_malformed_frame_without_crashing():
    in_queue = RedisDedupQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())
    await in_queue.push(_malformed_raw_frame())

    decoded = await _decode_once(in_queue, out_queue)

    assert decoded is True  # a frame was popped and handled, even though it failed to decode
    assert await out_queue.qsize() == 0


async def test_decode_once_on_empty_queue_is_a_noop():
    in_queue = RedisDedupQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())

    decoded = await _decode_once(in_queue, out_queue)

    assert decoded is False
    assert await out_queue.qsize() == 0
