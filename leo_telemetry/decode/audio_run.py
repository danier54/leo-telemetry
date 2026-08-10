"""Dedicated worker for CPU-intensive audio demodulation.

Keeping this consumer in a separate process ensures that a long recording can
delay only the audio queue, never the normal raw-frame decode queue.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

import httpx
from redis.asyncio import Redis

from leo_telemetry.common.models import RawFrame
from leo_telemetry.decode.afsk1200 import decode_audio, demodulate
from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.decode.frame_sync import extract_frames
from leo_telemetry.decode.redis_decoded_queue import RedisDecodedQueue
from leo_telemetry.ingest.redis_audio_queue import RedisAudioQueue

logger = logging.getLogger(__name__)


async def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

    poll_interval = float(
        os.environ.get("AUDIO_DECODE_POLL_INTERVAL_SECONDS", "2")
    )
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    redis_client = Redis.from_url(redis_url)
    in_queue = RedisAudioQueue(redis_client)
    out_queue = RedisDecodedQueue(redis_client)
    http_client = httpx.AsyncClient(timeout=30.0)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        while not stop_event.is_set():
            processed = await _decode_audio_once(
                in_queue, out_queue, http_client
            )
            if not processed:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=poll_interval
                    )
                except asyncio.TimeoutError:
                    pass
    finally:
        await http_client.aclose()
        await redis_client.aclose()


async def _decode_audio_once(
    in_queue: RedisAudioQueue,
    out_queue: RedisDecodedQueue,
    http_client: httpx.AsyncClient,
) -> bool:
    """Download and decode one queued audio observation."""
    observation = await in_queue.pop()
    if observation is None:
        return False

    try:
        response = await http_client.get(observation.payload_url)
        response.raise_for_status()

        samples, sample_rate_hz = decode_audio(response.content)
        bits = demodulate(samples, sample_rate_hz)
        frames = extract_frames(bits)
    except Exception:
        logger.exception(
            "Audio decode failed for observation=%s norad=%s",
            observation.observation_id,
            observation.norad_id,
        )
        return True

    decoded_count = 0
    for frame_bytes in frames:
        raw_frame = RawFrame(
            norad_id=observation.norad_id,
            observation_id=observation.observation_id,
            observer_station_id=observation.station_id,
            received_at=observation.observed_at,
            raw_bytes=frame_bytes,
        )
        try:
            decoded = decode_frame(raw_frame, has_fcs=True)
        except Exception:
            logger.exception(
                "AX.25 decode failed for audio observation=%s norad=%s",
                observation.observation_id,
                observation.norad_id,
            )
            continue
        if decoded is None:
            continue
        await out_queue.push(decoded)
        decoded_count += 1

    logger.info(
        "Decoded %d AX.25 frame(s) from audio observation=%s norad=%s",
        decoded_count,
        observation.observation_id,
        observation.norad_id,
    )
    return True


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
