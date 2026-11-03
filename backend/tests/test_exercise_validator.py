import os
import sys
import unittest

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.exercise_validator import (
    validate_pose_quality,
    validate_motion,
    mismatch_result,
)


def _make_frame(i: int, wr_y: float = 0.20, wl_y: float = 0.20, elbow_travel: float = 0.0):
    landmarks = {
        "shoulder_r": [0.55, 0.40 - elbow_travel * 0.20, 0.0, 0.99],
        "shoulder_l": [0.45, 0.40 - elbow_travel * 0.20, 0.0, 0.99],
        "hip_r": [0.55, 0.70 - elbow_travel * 0.20, 0.0, 0.99],
        "hip_l": [0.45, 0.70 - elbow_travel * 0.20, 0.0, 0.99],
        "elbow_r": [0.65 + elbow_travel * 0.15, 0.35 + elbow_travel * 0.10, 0.0, 0.99],
        "elbow_l": [0.35 - elbow_travel * 0.15, 0.35 + elbow_travel * 0.10, 0.0, 0.99],
        "wrist_r": [0.58, wr_y, 0.0, 0.99],
        "wrist_l": [0.42, wl_y, 0.0, 0.99],
    }
    world_landmarks = {
        "shoulder_r": [0.20, 0.10 - elbow_travel * 0.50, 0.0, 0.99],
        "shoulder_l": [-0.20, 0.10 - elbow_travel * 0.50, 0.0, 0.99],
        "hip_r": [0.15, 0.40, 0.0, 0.99],
        "hip_l": [-0.15, 0.40, 0.0, 0.99],
        "elbow_r": [0.35 + elbow_travel * 0.15, -0.10 + elbow_travel * 0.15, 0.0, 0.99],
        "elbow_l": [-0.35 - elbow_travel * 0.15, -0.10 + elbow_travel * 0.15, 0.0, 0.99],
        "wrist_r": [0.25, -0.40 + (wr_y - 0.20), 0.0, 0.99],
        "wrist_l": [-0.25, -0.40 + (wl_y - 0.20), 0.0, 0.99],
    }
    return {
        "frame_index": i,
        "timestamp_s": i / 30.0,
        "filtered_landmarks": landmarks,
        "landmarks": landmarks,
        "world_landmarks": world_landmarks,
    }


class ExerciseValidatorTests(unittest.TestCase):
    def test_pose_quality_rejects_empty_or_short_frames(self):
        res = validate_pose_quality([])
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "no_person")

        short_frames = [_make_frame(i) for i in range(5)]
        res = validate_pose_quality(short_frames)
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "no_person")

    def test_pose_quality_rejects_missing_upper_body(self):
        frames = [{"frame_index": i, "filtered_landmarks": {}} for i in range(20)]
        res = validate_pose_quality(frames)
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "no_person")
        self.assertIn("No lifter detected", res["message"])

    def test_pose_quality_accepts_good_lifter_tracking(self):
        frames = [_make_frame(i) for i in range(25)]
        res = validate_pose_quality(frames)
        self.assertTrue(res["valid"])

    def test_motion_validator_rejects_zero_reps(self):
        frames = [_make_frame(i) for i in range(30)]
        set_metrics = {"total_reps": 0, "reps_data": []}
        res = validate_motion(frames, set_metrics, "Lat Pulldown (Lower-Lat Bias)")
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "no_reps")

    def test_motion_validator_rejects_minimal_elbow_flexion_travel(self):
        # 30 frames, stationary elbows (zero bending range)
        frames = [_make_frame(i, elbow_travel=0.0) for i in range(30)]
        set_metrics = {
            "total_reps": 1,
            "reps_data": [{"start_idx": 0, "peak_idx": 15, "end_idx": 29}]
        }
        res = validate_motion(frames, set_metrics, "Lat Pulldown (Lower-Lat Bias)")
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "exercise_mismatch")

    def test_motion_validator_flags_row_selected_for_overhead_movement(self):
        # Frames with wrists consistently above shoulders (shoulder_y=0.30, wrist_y=0.10)
        frames = []
        for i in range(30):
            t = (i % 30) / 30.0
            travel = 0.35 * np.sin(t * np.pi)
            frames.append(_make_frame(i, wr_y=0.10 + travel, wl_y=0.10 + travel, elbow_travel=travel))

        set_metrics = {
            "total_reps": 1,
            "reps_data": [{"start_idx": 0, "peak_idx": 15, "end_idx": 29}]
        }
        # Selected exercise is a Row, but arms are overhead!
        res = validate_motion(frames, set_metrics, "Barbell Row")
        self.assertFalse(res["valid"])
        self.assertEqual(res["reason_code"], "exercise_mismatch")
        self.assertIn("vertical pulling movement", res["message"])

    def test_motion_validator_accepts_valid_pull_reps(self):
        frames = []
        for i in range(30):
            t = (i % 30) / 30.0
            travel = 0.35 * np.sin(t * np.pi)
            frames.append(_make_frame(i, wr_y=0.15 + travel, wl_y=0.15 + travel, elbow_travel=travel))

        set_metrics = {
            "total_reps": 1,
            "reps_data": [{"start_idx": 0, "peak_idx": 15, "end_idx": 29}]
        }
        res = validate_motion(frames, set_metrics, "Lat Pulldown (Lower-Lat Bias)")
        self.assertTrue(res["valid"])


if __name__ == "__main__":
    unittest.main()
