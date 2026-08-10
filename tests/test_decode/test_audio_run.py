from datetime import datetime, timezone

import httpx
from fakeredis import FakeAsyncRedis

from leo_telemetry.decode.audio_run import _decode_audio_once
from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue
from leo_telemetry.ingest.audio_client import AudioObservation
from leo_telemetry.ingest.redis_audio_queue import RedisAudioQueue
from tests.test_decode.helpers import build_ax25_frame, shifted_address


def _audio_observation() -> AudioObservation:
    return AudioObservation(
        norad_id=25544,
        observation_id=123,
        station_id=42,
        observed_at=datetime.now(timezone.utc),
        payload_url="https://example.test/iss.ogg",
    )


async def test_decode_audio_once_pushes_valid_frames(monkeypatch):
    in_queue = RedisAudioQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())
    await in_queue.push(_audio_observation())

    valid_frame = build_ax25_frame(
        addresses=[
            shifted_address("CQ", 0, last=False),
            shifted_address("KJ6ABC", 0, last=True),
        ],
        control_pid=b"\x03\xf0",
        info=b"hello from audio",
        append_fcs=True,
    )
    invalid_frame = valid_frame[:-1] + bytes([valid_frame[-1] ^ 0xFF])

    monkeypatch.setattr(
        "leo_telemetry.decode.audio_run.decode_audio",
        lambda _: (object(), 22050),
    )
    monkeypatch.setattr(
        "leo_telemetry.decode.audio_run.demodulate", lambda *_: "bits"
    )
    monkeypatch.setattr(
        "leo_telemetry.decode.audio_run.extract_frames",
        lambda _: [valid_frame, invalid_frame],
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"ogg", request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        processed = await _decode_audio_once(in_queue, out_queue, client)

    assert processed is True
    assert await out_queue.qsize() == 1
    result = await out_queue.pop()
    assert result.norad_id == 25544
    assert result.src_callsign == "KJ6ABC"
    assert result.payload == b"hello from audio"


async def test_decode_audio_once_on_empty_queue_is_a_noop():
    in_queue = RedisAudioQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())

    async with httpx.AsyncClient() as client:
        processed = await _decode_audio_once(in_queue, out_queue, client)

    assert processed is False
    assert await out_queue.qsize() == 0


async def test_decode_audio_once_drops_failed_download():
    in_queue = RedisAudioQueue(FakeAsyncRedis())
    out_queue = RedisDecodedQueue(FakeAsyncRedis())
    await in_queue.push(_audio_observation())

    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, request=request)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        processed = await _decode_audio_once(in_queue, out_queue, client)

    assert processed is True
    assert await out_queue.qsize() == 0
