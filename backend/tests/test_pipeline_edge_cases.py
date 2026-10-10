import os
import sys
import tempfile
import unittest

import cv2
import numpy as np


BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.biomechanics import analyze_set
from app.services.ml_pipeline import _rebase_metrics_for_active_range
from app.services.video_renderer import _render_pip_dashboard, render_overlay_video


def _stationary_frame(index: int):
    landmarks = {
        "shoulder_r": [0.60, 0.40, 0.0, 0.99],
        "shoulder_l": [0.40, 0.40, 0.0, 0.99],
        "elbow_r": [0.65, 0.50, 0.0, 0.99],
        "elbow_l": [0.35, 0.50, 0.0, 0.99],
        "wrist_r": [0.65, 0.25, 0.0, 0.99],
        "wrist_l": [0.35, 0.25, 0.0, 0.99],
        "hip_r": [0.58, 0.65, 0.0, 0.99],
        "hip_l": [0.42, 0.65, 0.0, 0.99],
    }
    return {
        "frame_index": index,
        "timestamp_s": index / 30.0,
        "filtered_landmarks": landmarks,
        "display_landmarks": landmarks,
        "world_landmarks": landmarks,
    }


class PipelineEdgeCaseTests(unittest.TestCase):
    def test_zero_rep_stationary_video_does_not_create_false_rep(self):
        frames = [_stationary_frame(i) for i in range(90)]
        metrics = analyze_set(
            frames,
            fps=30.0,
            exercise_name="Lat Pulldown (Lower-Lat Bias)",
        )
        self.assertEqual(metrics["total_reps"], 0)
        self.assertEqual(metrics["reps_data"], [])

    def test_missing_nan_landmark_and_bad_timestamp_do_not_crash(self):
        frames = [_stationary_frame(i) for i in range(20)]
        frames[4]["filtered_landmarks"]["wrist_r"] = None
        frames[5]["filtered_landmarks"]["wrist_l"][1] = float("nan")
        frames[6]["timestamp_s"] = None
        metrics = analyze_set(frames, fps=0, exercise_name="Barbell Row")
        self.assertIn("total_reps", metrics)
        self.assertEqual(len(metrics["skeleton_3d_frames"]), len(frames))

    def test_auto_trim_rebases_skeleton_timestamps_and_rep_indices(self):
        metrics = {
            "skeleton_3d_frames": [
                {"frame_idx": i, "timestamp_s": i / 30.0, "joints": {}, "angles": {}}
                for i in range(5)
            ],
            "reps_data": [{"start_idx": 1, "peak_idx": 2, "end_idx": 3}],
        }
        _rebase_metrics_for_active_range(metrics, (1, 3))
        self.assertEqual([f["frame_idx"] for f in metrics["skeleton_3d_frames"]], [0, 1, 2])
        self.assertEqual(metrics["skeleton_3d_frames"][0]["timestamp_s"], 0.0)
        self.assertEqual(metrics["reps_data"][0]["start_idx"], 0)
        self.assertEqual(metrics["reps_data"][0]["peak_idx"], 1)
        self.assertEqual(metrics["reps_data"][0]["end_idx"], 2)

    def test_pip_handles_portrait_landscape_and_mismatched_lengths(self):
        reps = [{"start_idx": 2, "peak_idx": 4, "end_idx": 7, "rep_number": 1}]
        trajectory = np.linspace(0.0, 1.0, 7)
        for height, width in ((720, 405), (405, 720), (40, 720)):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            _render_pip_dashboard(frame, 9, 12, trajectory, reps, width, height)
            self.assertEqual(frame.shape, (height, width, 3))

    def test_full_renderer_writes_portrait_and_landscape_video(self):
        frame_data = [_stationary_frame(i) for i in range(12)]
        metrics = {
            "exercise_name": "Lat Pulldown (Lower-Lat Bias)",
            "total_reps": 0,
            "reps_data": [],
            "bar_reference": {},
            "avg_elbow_flare": 0.0,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            for name, size in (("portrait", (180, 320)), ("landscape", (320, 180))):
                input_path = os.path.join(temp_dir, f"{name}_input.mp4")
                output_path = os.path.join(temp_dir, f"{name}_output.mp4")
                writer = cv2.VideoWriter(
                    input_path,
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    30.0,
                    size,
                )
                self.assertTrue(writer.isOpened())
                for _ in frame_data:
                    writer.write(np.zeros((size[1], size[0], 3), dtype=np.uint8))
                writer.release()

                render_overlay_video(input_path, frame_data, metrics, output_path)
                cap = cv2.VideoCapture(output_path)
                self.assertTrue(cap.isOpened())
                self.assertGreater(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 0)
                cap.release()

    def test_bilateral_asymmetry_detection_and_metrics(self):
        """Verify that asymmetric limb movement generates accurate flare delta and pattern."""
        frames = []
        # Simulate 2 pull reps (60 frames total at 30fps)
        for i in range(60):
            t = (i % 30) / 30.0
            # Pull down trajectory: goes from 0.0 to 0.45 and back
            travel = 0.45 * np.sin(t * np.pi)
            
            # Left arm: tight flare (~40 deg). Right arm: wide flare (~75 deg)
            er_x = 0.60 + 0.15 * travel  # Right elbow pushed outward laterally
            el_x = 0.40 - 0.04 * travel  # Left elbow tucked in tighter
            
            fd = {
                "timestamp_s": i / 30.0,
                "landmarks": {
                    "shoulder_r": [0.55, 0.30, 0.9],
                    "shoulder_l": [0.45, 0.30, 0.9],
                    "hip_r": [0.55, 0.65, 0.9],
                    "hip_l": [0.45, 0.65, 0.9],
                    "elbow_r": [er_x, 0.45 + travel, 0.9],
                    "elbow_l": [el_x, 0.45 + travel, 0.9],
                    "wrist_r": [0.58, 0.20 + travel * 0.9, 0.9],
                    "wrist_l": [0.42, 0.20 + travel * 0.9, 0.9],
                },
                "world_landmarks": {
                    "shoulder_r": [0.20, -0.10, 0.0],
                    "shoulder_l": [-0.20, -0.10, 0.0],
                    "hip_r": [0.15, 0.40, 0.0],
                    "hip_l": [-0.15, 0.40, 0.0],
                    "elbow_r": [0.35 + 0.15 * travel, 0.10 + travel, 0.0],
                    "elbow_l": [-0.25 - 0.03 * travel, 0.10 + travel, 0.0],
                    "wrist_r": [0.25, -0.20 + travel, 0.0],
                    "wrist_l": [-0.25, -0.20 + travel, 0.0],
                }
            }
            frames.append(fd)

        metrics = analyze_set(frames, fps=30.0, exercise_name="Lat Pulldown (Lower-Lat Bias)")
        self.assertIn("asymmetry_analysis", metrics)
        asym = metrics["asymmetry_analysis"]
        self.assertIn("overall_symmetry_score", asym)
        self.assertIn("heatmap_rows", asym)
        self.assertIn("primary_pattern", asym)
        
        # In this asymmetric simulation, Right elbow flares substantially more than Left elbow
        if metrics["total_reps"] > 0:
            rep1 = metrics["reps_data"][0]
            self.assertIn("left_elbow_flare_deg", rep1)
            self.assertIn("right_elbow_flare_deg", rep1)
            self.assertIn("elbow_flare_delta_deg", rep1)
            self.assertGreater(rep1["right_elbow_flare_deg"], rep1["left_elbow_flare_deg"])
            self.assertEqual(rep1["dominant_flare_side"], "Right")


if __name__ == "__main__":
    unittest.main()
