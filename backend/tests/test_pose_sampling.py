import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.video_processor import PoseExtractor
from app.services.video_timing import active_frame_range, frame_times, render_schedule
from app.services.biomechanics import analyze_set
from app.services.video_renderer import render_overlay_video


class FakeCapture:
    def __init__(self, fps, times):
        self.fps = fps
        self.times = times
        self.index = -1
        self.retrieved = []
        self.released = False

    def isOpened(self):
        return not self.released

    def get(self, prop):
        return {cv2.CAP_PROP_FPS: self.fps, cv2.CAP_PROP_FRAME_WIDTH: 32,
                cv2.CAP_PROP_FRAME_HEIGHT: 32,
                cv2.CAP_PROP_POS_MSEC: self.times[max(0, self.index)] * 1000}.get(prop, 0)

    def grab(self):
        self.index += 1
        return self.index < len(self.times)

    def retrieve(self):
        self.retrieved.append(self.index)
        return True, np.zeros((32, 32, 3), dtype=np.uint8)

    def release(self):
        self.released = True


class PoseSamplingTests(unittest.TestCase):
    def extract(self, source_fps, target_fps, times=None, detector=None):
        capture = FakeCapture(source_fps, times if times is not None else np.arange(round(source_fps * 2)) / source_fps)
        extractor = object.__new__(PoseExtractor)
        extractor.target_fps = target_fps
        extractor.last_profile = {}
        detector = detector or SimpleNamespace(detect_for_video=lambda image, ts: SimpleNamespace(pose_landmarks=[]))
        with patch("app.services.video_processor.cv2.VideoCapture", return_value=capture):
            frames = extractor._extract_with_detector("unused", detector)
        self.assertTrue(capture.released)
        self.assertEqual(len(capture.retrieved), len(frames))
        return frames, extractor

    def test_twenty_fps_is_not_rounded_to_fifteen(self):
        for fps in (24, 29.97, 30, 60, 120):
            with self.subTest(source_fps=fps):
                frames, extractor = self.extract(fps, 20)
                self.assertEqual(len(frames), 40)
                self.assertEqual(frames[0]["timestamp_s"], 0)
                self.assertLessEqual(abs(extractor.last_profile["source_duration_s"] - 2), 1 / fps)
                times = frame_times(frames)
                for i, timestamp in enumerate(times):
                    self.assertGreaterEqual(timestamp + 1e-7, i / 20)
                    self.assertLess(timestamp - i / 20, 1 / fps + 1e-7)
                self.assertEqual([f["source_frame_index"] for f in frames], sorted(set(f["source_frame_index"] for f in frames)))

    def test_variable_frame_times_are_preserved(self):
        times = [0, .02, .06, .09, .11, .15, .21]
        frames, _ = self.extract(30, 20, times)
        self.assertEqual([f["timestamp_s"] for f in frames], [0, .06, .11, .15, .21])

    def test_near_thirty_fps_metadata_does_not_drop_tracking_frames(self):
        frames, _ = self.extract(30.032, 30)
        self.assertEqual(len(frames), 60)

    def test_capture_is_released_when_inference_fails(self):
        capture = FakeCapture(30, [0])
        extractor = object.__new__(PoseExtractor)
        extractor.target_fps = 30
        extractor.last_profile = {}
        def fail(image, timestamp):
            raise RuntimeError("inference failed")
        with patch("app.services.video_processor.cv2.VideoCapture", return_value=capture):
            with self.assertRaises(RuntimeError):
                extractor._extract_with_detector("unused", SimpleNamespace(detect_for_video=fail))
        self.assertTrue(capture.released)

    def test_zero_confidence_is_not_promoted_to_visible(self):
        landmark = SimpleNamespace(x=.5, y=.5, z=0, visibility=0.0, presence=1.0)
        detector = SimpleNamespace(detect_for_video=lambda image, ts: SimpleNamespace(
            pose_landmarks=[[landmark] * 33], pose_world_landmarks=[]))
        frames, _ = self.extract(30, 20, [0], detector)
        self.assertEqual(frames[0]["confidences"]["shoulder_l"], 0.0)
        self.assertIsNone(frames[0]["filtered_landmarks"]["shoulder_l"])

    def test_display_interpolation_uses_elapsed_time_only(self):
        frames = [{"timestamp_s": t, "filtered_landmarks": {"wrist_l": point}}
                  for t, point in ((0, [0, 0, 0, 1]), (.1, None), (.4, [1, 1, 1, 1]))]
        extractor = object.__new__(PoseExtractor)
        extractor._build_display_landmarks(frames)
        self.assertEqual(frames[1]["display_landmarks"]["wrist_l"], [.25, .25, .25, 0])
        self.assertIsNone(frames[1]["filtered_landmarks"]["wrist_l"])

    def test_trim_padding_is_one_second_at_each_cadence(self):
        for fps in (15, 20, 30):
            frames = [{"timestamp_s": i / fps} for i in range(10 * fps)]
            active = active_frame_range(frames, [{"start_idx": 3 * fps, "end_idx": 6 * fps}])
            self.assertEqual(active, (2 * fps, 7 * fps))

    def test_render_schedule_preserves_time_and_source_mapping(self):
        frames, _ = self.extract(30, 20)
        fps, schedule = render_schedule(frames, 0, len(frames) - 1, 30)
        self.assertEqual(fps, 20)
        self.assertEqual(len(schedule), 40)
        for i, (source_idx, pose_idx) in enumerate(schedule):
            self.assertEqual(source_idx, frames[pose_idx]["source_frame_index"])
            self.assertLessEqual(frames[pose_idx]["timestamp_s"], i / fps + 1e-7)
        fps, trimmed = render_schedule(frames, 10, 29, 30)
        self.assertAlmostEqual(len(trimmed) / fps, 1.0)
        self.assertEqual(trimmed[0][1], 10)

    def test_real_encoder_preserves_lower_cadence_duration(self):
        frames, _ = self.extract(30, 20)
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source.mp4")
            output = os.path.join(directory, "output.mp4")
            writer = cv2.VideoWriter(source, cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 120))
            self.assertTrue(writer.isOpened())
            for _ in range(60):
                writer.write(np.zeros((120, 160, 3), dtype=np.uint8))
            writer.release()
            render_overlay_video(source, frames, {"total_reps": 0}, output, (10, 29))
            capture = cv2.VideoCapture(output)
            self.assertTrue(capture.isOpened())
            self.assertAlmostEqual(capture.get(cv2.CAP_PROP_FPS), 20, places=3)
            self.assertEqual(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 20)
            capture.release()

    def test_synthetic_rep_metrics_stay_close_across_cadences(self):
        results = []
        for fps in (30, 20, 15):
            frames = []
            for i in range(8 * fps):
                t = i / fps
                travel = .25 * (1 - np.cos(t * np.pi))
                landmarks = {
                    "shoulder_r": [.6, .3, 0, 1], "shoulder_l": [.4, .3, 0, 1],
                    "hip_r": [.6, .7, 0, 1], "hip_l": [.4, .7, 0, 1],
                    "wrist_r": [.6, .1 + travel, 0, 1], "wrist_l": [.4, .1 + travel, 0, 1],
                }
                frames.append({"timestamp_s": t, "filtered_landmarks": landmarks})
            results.append(analyze_set(frames, fps=fps, exercise_name="Lat Pulldown"))
        baseline = results[0]
        self.assertGreater(baseline["total_reps"], 0)
        for result in results[1:]:
            self.assertEqual(result["total_reps"], baseline["total_reps"])
            self.assertEqual(result["full_reps"], baseline["full_reps"])
            for reference, rep in zip(baseline["reps_data"], result["reps_data"]):
                self.assertAlmostEqual(reference["concentric_tempo_s"], rep["concentric_tempo_s"], delta=.1)
                self.assertAlmostEqual(reference["mean_velocity_mps"], rep["mean_velocity_mps"], delta=.05)


if __name__ == "__main__":
    unittest.main()
