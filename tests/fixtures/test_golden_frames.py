from leo_telemetry.common.models import RawFrame
from tests.fixtures.golden_frames import load_golden_frames


def test_load_golden_frames_returns_raw_frames_for_all_target_satellites():
    frames = load_golden_frames()

    assert len(frames) > 0
    assert all(isinstance(frame, RawFrame) for frame in frames)
    assert {frame.norad_id for frame in frames} == {60525, 68458, 31130}
