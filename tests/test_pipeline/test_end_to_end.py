"""True end-to-end pipeline tests: ingest -> decode -> demux.

`tests/test_demux/test_golden_frames.py` already checks that
decode_frame() and demultiplex() individually produce sane values for
real captures. This file checks the seam between all three stages
together: that a captured frame's identity survives the whole trip
from the ingest dedup queue through to the TelemetryReading that
observability and scoring consume next.
"""

from __future__ import annotations

from leo_telemetry.decode.ax25 import decode_frame
from leo_telemetry.demux.demux import demultiplex
from leo_telemetry.ingest.dedup import DedupQueue
from tests.fixtures.golden_frames import load_golden_frames

# Satellites with at least one golden capture that decodes and
# demultiplexes cleanly end to end. CAPE-1 is left out here for the same
# reason it's skipped in test_golden_frames.py: none of its three golden
# captures are real telemetry, just RF noise.
PIPELINE_NORAD_IDS = (60525, 68458)


def test_pipeline_preserves_frame_identity_end_to_end() -> None:
    """norad_id and received_at must survive ingest -> decode -> demux unchanged."""
    queue = DedupQueue()
    for raw_frame in load_golden_frames():
        queue.push(raw_frame)

    checked = 0
    while (raw_frame := queue.pop()) is not None:
        if raw_frame.norad_id not in PIPELINE_NORAD_IDS:
            continue

        decoded_frame = decode_frame(raw_frame)
        if decoded_frame is None:
            continue

        reading = demultiplex(decoded_frame)
        if reading is None:
            continue

        checked += 1
        assert decoded_frame.norad_id == raw_frame.norad_id
        assert decoded_frame.received_at == raw_frame.received_at
        assert reading.norad_id == raw_frame.norad_id
        assert reading.received_at == raw_frame.received_at

    assert checked > 0, "no golden frame made it end to end -- pipeline is broken"


def test_dedup_queue_drops_repeat_captures_before_they_reach_decode() -> None:
    """Overlapping ground-station captures of the same frame must not double-count downstream."""
    frames = [f for f in load_golden_frames() if f.norad_id == 68458]
    assert frames, "need at least one CP16 golden frame for this test"
    frame = frames[0]

    queue = DedupQueue()
    assert queue.push(frame) is True, "first capture should be accepted"
    assert queue.push(frame) is False, "duplicate capture should be rejected"
    assert len(queue) == 1

    popped = queue.pop()
    assert popped is not None
    assert popped.dedup_key == frame.dedup_key
    assert queue.pop() is None, "queue should be empty after the single unique frame is popped"
