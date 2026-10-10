"""Shared sampling/timeline helpers; measurement indices are not video frames."""

import bisect
import math
from statistics import median


def frame_times(frames, fallback_fps=30.0):
    fps = fallback_fps if math.isfinite(fallback_fps) and fallback_fps > 0 else 30.0
    times = []
    for i, frame in enumerate(frames):
        try:
            value = float(frame.get("timestamp_s", i / fps))
        except (TypeError, ValueError):
            value = float("nan")
        if not math.isfinite(value) or (times and value <= times[-1]):
            value = times[-1] + 1.0 / fps if times else i / fps
        times.append(value)
    return times


def sampling_fps(frames, fallback=30.0):
    """Use elapsed time, rather than median gaps (20/30 sampling alternates gaps)."""
    times = frame_times(frames, fallback)
    if len(times) > 1:
        return (len(times) - 1) / (times[-1] - times[0])
    return fallback


def timeline_end(frames, times=None, fallback_fps=30.0):
    if not frames:
        return 0.0
    times = times if times is not None else frame_times(frames, fallback_fps)
    duration = frames[-1].get("duration_s")
    if duration is None:
        duration = median(b - a for a, b in zip(times, times[1:])) if len(times) > 1 else 1.0 / fallback_fps
    return times[-1] + float(duration)


def active_frame_range(frames, reps, padding_s=1.0):
    if not frames or not reps:
        return None
    times = frame_times(frames)
    start_time = times[reps[0]["start_idx"]] - padding_s
    end_time = times[reps[-1]["end_idx"]] + padding_s
    start = max(0, bisect.bisect_right(times, start_time) - 1)
    end = min(len(frames) - 1, bisect.bisect_left(times, end_time))
    return (start, end) if end > start and (start > 0 or end < len(frames) - 1) else None


def render_schedule(frames, start, end, source_fps):
    """Resample selected source images/poses onto a constant-rate encoding clock.

    Repeated images hold the latest measured pose; measurements are never interpolated.
    Legacy data without source indices keeps its original stride mapping.
    """
    times = frame_times(frames)
    fps = float(frames[0].get("sample_fps", source_fps / max(1, round(source_fps / 30.0))))
    stop = times[end + 1] if end + 1 < len(times) else timeline_end(frames, times, fps)
    count = max(1, math.ceil((stop - times[start]) * fps - 1e-7))
    legacy_step = max(1, round(source_fps / 30.0))
    schedule = []
    for i in range(count):
        timestamp = times[start] + i / fps
        pose_idx = min(end, max(start, bisect.bisect_right(times, timestamp + 1e-7) - 1))
        source_idx = int(frames[pose_idx].get("source_frame_index", pose_idx * legacy_step))
        schedule.append((source_idx, pose_idx))
    return fps, schedule
