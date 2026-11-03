"""
Input validation gates for the analysis pipeline.

These run *before* any coaching or rendering so that videos which don't contain a
lifter, or don't contain the selected exercise, are flagged instead of producing
made-up metrics. All gates are deliberately conservative: a false rejection of a
real set is worse than letting an odd clip through, so thresholds sit well below
what genuine pulling movements produce.
"""
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.biomechanics import calculate_estimated_3d_elbow_flexion

# Upper-body joints every supported exercise relies on.
_KEY_JOINTS = ("shoulder_r", "shoulder_l", "elbow_r", "elbow_l", "wrist_r", "wrist_l")

# Pose-quality gate
MIN_FRAMES = 10
MIN_TRACKED_FRAME_RATIO = 0.35  # share of frames where the upper body is tracked

# Motion-plausibility gate
MIN_ELBOW_FLEXION_RANGE_DEG = 20.0  # every pull bends the elbow far more than this
MIN_PLAUSIBLE_REP_RATIO = 0.5  # share of reps that must look like a pull
# Median (shoulder_y - wrist_y) across rep frames, in normalised image units.
VERTICAL_MIN_WRIST_HEIGHT = -0.05  # pulldowns/pull-ups measured 0.10-0.38 on benchmark clips
ROW_MAX_WRIST_HEIGHT = 0.0  # rows keep the hands below the shoulders


def _result(valid: bool, reason_code: Optional[str] = None, message: str = "",
            detected_exercise: Optional[str] = None, **details: Any) -> Dict[str, Any]:
    return {
        "valid": valid,
        "reason_code": reason_code,
        "message": message,
        "detected_exercise": detected_exercise,
        "details": details,
    }


def valid_result() -> Dict[str, Any]:
    return _result(True)


def mismatch_result(selected_exercise: str, detected_exercise: Optional[str] = None,
                    source: str = "rules", **details: Any) -> Dict[str, Any]:
    friendly = selected_exercise.split(" (")[0]
    if detected_exercise:
        message = f"Exercise doesn't match: this looks like {detected_exercise}, not {friendly}."
    else:
        message = f"Exercise doesn't match: this doesn't look like {friendly}."
    return _result(False, "exercise_mismatch", message, detected_exercise, source=source, **details)


def _lm(fd: Dict[str, Any], name: str):
    lm = fd.get("filtered_landmarks") or fd.get("landmarks") or {}
    return lm.get(name)


def _upper_body_tracked(fd: Dict[str, Any]) -> bool:
    has_shoulders = _lm(fd, "shoulder_r") is not None and _lm(fd, "shoulder_l") is not None
    has_arm = any(
        _lm(fd, f"elbow_{s}") is not None and _lm(fd, f"wrist_{s}") is not None for s in ("r", "l")
    )
    return has_shoulders and has_arm


def validate_pose_quality(frame_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reject clips where no lifter's upper body is visible for most of the video."""
    n = len(frame_data or [])
    if n < MIN_FRAMES:
        return _result(False, "no_person", "Video is too short to analyse. Please upload a full set.",
                       frames=n)

    tracked = sum(1 for fd in frame_data if _upper_body_tracked(fd))
    ratio = tracked / n
    if ratio < MIN_TRACKED_FRAME_RATIO:
        return _result(
            False, "no_person",
            "No lifter detected. Make sure your whole upper body is clearly visible in the frame.",
            tracked_frame_ratio=round(ratio, 3),
        )
    return _result(True, tracked_frame_ratio=round(ratio, 3))


def _elbow_flexion_series(frame_data: List[Dict[str, Any]], side: str) -> np.ndarray:
    values = []
    for fd in frame_data:
        world = fd.get("world_landmarks") or {}
        lm = fd.get("filtered_landmarks") or fd.get("landmarks") or {}
        s = world.get(f"shoulder_{side}") or lm.get(f"shoulder_{side}")
        e = world.get(f"elbow_{side}") or lm.get(f"elbow_{side}")
        w = world.get(f"wrist_{side}") or lm.get(f"wrist_{side}")
        if s and e and w:
            angle, _ = calculate_estimated_3d_elbow_flexion(s, e, w)
            values.append(float(angle) if angle is not None else np.nan)
        else:
            values.append(np.nan)
    return np.array(values, dtype=float)


def _window_range(series: np.ndarray, start: int, end: int) -> float:
    window = series[max(0, start):end + 1]
    window = window[np.isfinite(window)]
    if len(window) < 2:
        return 0.0
    return float(np.percentile(window, 95) - np.percentile(window, 5))


def _median_wrist_above_shoulder(frame_data: List[Dict[str, Any]], indices: List[int]) -> Optional[float]:
    """Median of (shoulder_y - wrist_y) at the given frames. Positive means wrists above shoulders."""
    diffs = []
    for idx in indices:
        if not (0 <= idx < len(frame_data)):
            continue
        fd = frame_data[idx]
        for side in ("r", "l"):
            s, w = _lm(fd, f"shoulder_{side}"), _lm(fd, f"wrist_{side}")
            if s and w and np.isfinite(s[1]) and np.isfinite(w[1]):
                diffs.append(float(s[1]) - float(w[1]))
    return float(np.median(diffs)) if diffs else None


def validate_motion(frame_data: List[Dict[str, Any]], set_metrics: Dict[str, Any],
                    exercise_name: str) -> Dict[str, Any]:
    """Check that the detected reps look like the selected pulling exercise."""
    reps = set_metrics.get("reps_data") or []
    if not reps or int(set_metrics.get("total_reps", 0) or 0) == 0:
        friendly = exercise_name.split(" (")[0]
        return _result(
            False, "no_reps",
            f"No {friendly} reps detected. Make sure the full movement is in frame, "
            "or check you selected the right exercise.",
        )

    # 1. Every supported exercise is a pull: the elbow must bend substantially during each rep.
    flex_r = _elbow_flexion_series(frame_data, "r")
    flex_l = _elbow_flexion_series(frame_data, "l")
    rep_ranges = []
    for rep in reps:
        start, end = int(rep.get("start_idx", 0)), int(rep.get("end_idx", 0))
        rep_ranges.append(max(_window_range(flex_r, start, end), _window_range(flex_l, start, end)))
    plausible = sum(1 for r in rep_ranges if r >= MIN_ELBOW_FLEXION_RANGE_DEG)
    plausible_ratio = plausible / len(rep_ranges)
    if plausible_ratio < MIN_PLAUSIBLE_REP_RATIO:
        return mismatch_result(
            exercise_name,
            median_elbow_range_deg=round(float(np.median(rep_ranges)), 1),
            plausible_rep_ratio=round(plausible_ratio, 2),
        )

    # 2. Vertical vs horizontal pull: throughout a pulldown/pull-up the hands stay around or
    #    above head height, while in every row they stay below the shoulders.
    ex = (exercise_name or "").lower()
    is_vertical = "pulldown" in ex or "pull-up" in ex or "chin" in ex
    is_row = "row" in ex
    rep_frames: List[int] = []
    for r in reps:
        rep_frames.extend(range(int(r.get("start_idx", 0)), int(r.get("end_idx", 0)) + 1))
    wrist_height = _median_wrist_above_shoulder(frame_data, rep_frames)
    if wrist_height is not None:
        # Margin in normalised image units so side-on or tilted cameras don't trip the check.
        if is_vertical and wrist_height < VERTICAL_MIN_WRIST_HEIGHT:
            return mismatch_result(exercise_name, "a row or other horizontal movement",
                                   wrist_above_shoulder=round(wrist_height, 3))
        if is_row and wrist_height > ROW_MAX_WRIST_HEIGHT:
            return mismatch_result(exercise_name, "an overhead or vertical pulling movement",
                                   wrist_above_shoulder=round(wrist_height, 3))

    return _result(True, plausible_rep_ratio=round(plausible_ratio, 2),
                   wrist_above_shoulder=wrist_height)
