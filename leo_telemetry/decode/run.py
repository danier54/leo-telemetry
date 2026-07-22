"""
Local dev script: consume raw frames from the Redis queue, run them
through the AX.25 decoder, and print the results.

Usage:
    uv run python -m leo_telemetry.decode.run
"""

import asyncio
import os

from redis.asyncio import Redis

from leo_telemetry.ingest.redis_dedup import RedisDedupQueue
from leo_telemetry.decode.ax25 import decode_frame


async def main() -> None:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    queue = RedisDedupQueue(Redis.from_url(redis_url))

    print(f"Connected to Redis at {redis_url}\n")

    while True:
        frame = await queue.pop()

        if frame is None:
            print("Queue is empty, exiting.")
            break

        print("Raw frame in: \n", frame)

        print("Decoding")
        for _ in range(3):
            print(".", end="", flush=True)
            await asyncio.sleep(0.5)
        print()

        result = decode_frame(frame)

        print("Result:")
        if result is None:
            print(
                f"[obs={frame.observation_id}] FAILED to decode "
                f"raw={frame.raw_bytes.hex()}"
            )
        else:
            print(
                f"[obs={frame.observation_id}] "
                f"norad={result.norad_id} "
                f"src={result.src_callsign!r} "
                f"dest={result.dest_callsign!r} "
                f"payload={result.payload.hex()}"
            )

        for _ in range(3):
            print(".", end="", flush=True)
            await asyncio.sleep(0.5)
        print()


if __name__ == "__main__":
    asyncio.run(main())
