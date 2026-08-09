#!/usr/bin/env python3
"""Launch the live telemetry pipeline as detached worker processes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]


def start_process(command: Sequence[str], log_path: Path) -> subprocess.Popen[str]:
    """Start a child process in a detached session and redirect its stdout/stderr."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")
    handle.write(f"Starting {' '.join(command)}\n")
    handle.flush()

    return subprocess.Popen(
        list(command),
        cwd=str(ROOT),
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ.copy(),
    )


def main() -> None:
    env = os.environ.copy()
    env.setdefault("REDIS_URL", "redis://localhost:6379/0")
    env.setdefault("POLL_INTERVAL_SECONDS", "30")
    env.setdefault("MIN_REQUEST_INTERVAL_SECONDS", "5")
    env.setdefault("DECODE_POLL_INTERVAL_SECONDS", "2")
    env.setdefault("DEMUX_POLL_INTERVAL_SECONDS", "2")
    env.setdefault("EXPORTER_POLL_INTERVAL_SECONDS", "1")
    env.setdefault("EXPORTER_PORT", "8000")
    env.setdefault("LOG_LEVEL", "INFO")

    commands = [
        ([sys.executable, "-m", "leo_telemetry.ingest.run"], Path("/tmp/leo-ingest.log")),
        ([sys.executable, "-m", "leo_telemetry.decode.run"], Path("/tmp/leo-decode.log")),
        ([sys.executable, "-m", "leo_telemetry.decode.audio_run"], Path("/tmp/leo-audio-decode.log")),
        ([sys.executable, "-m", "leo_telemetry.demux.run"], Path("/tmp/leo-demux.log")),
        ([sys.executable, "scripts/live_dashboard.py"], Path("/tmp/leo-exporter.log")),
    ]

    started: list[subprocess.Popen[str]] = []
    for command, log_path in commands:
        proc = start_process(command, log_path)
        started.append(proc)
        print(f"Started {command[-1]} with pid {proc.pid}")

    for proc in started:
        proc.poll()


if __name__ == "__main__":
    main()
