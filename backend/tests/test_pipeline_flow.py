import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.models import BiomechanicsLog, Workout
from app.services.ml_pipeline import process_video_task
from app.services.coach_agent import BiomechanicsFeedback, ScorecardTier


def _create_synthetic_test_video(path: str, num_frames: int = 10, width: int = 160, height: int = 120):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (width, height))
    for _ in range(num_frames):
        writer.write(np.zeros((height, width, 3), dtype=np.uint8))
    writer.release()


def _mock_frame_data(num_frames: int = 30):
    frames = []
    for i in range(num_frames):
        t = (i % 30) / 30.0
        travel = 0.40 * np.sin(t * np.pi)
        landmarks = {
            "shoulder_r": [0.55, 0.30, 0.0, 0.99],
            "shoulder_l": [0.45, 0.30, 0.0, 0.99],
            "hip_r": [0.55, 0.65, 0.0, 0.99],
            "hip_l": [0.45, 0.65, 0.0, 0.99],
            "elbow_r": [0.60, 0.45 + travel, 0.0, 0.99],
            "elbow_l": [0.40, 0.45 + travel, 0.0, 0.99],
            "wrist_r": [0.58, 0.20 + travel * 0.9, 0.0, 0.99],
            "wrist_l": [0.42, 0.20 + travel * 0.9, 0.0, 0.99],
        }
        frames.append({
            "frame_index": i,
            "timestamp_s": i / 30.0,
            "timestamp_ms": int((i / 30.0) * 1000),
            "filtered_landmarks": landmarks,
            "display_landmarks": landmarks,
            "world_landmarks": landmarks,
            "landmarks": landmarks,
        })
    return frames


class PipelineFlowTests(unittest.IsolatedAsyncioTestCase):
    """Fast, offline unit tests for the two-phase async pipeline state machine."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.video_path = os.path.join(self.temp_dir.name, "test_clip.mp4")
        _create_synthetic_test_video(self.video_path, num_frames=10)

        # Mock DB entities
        self.mock_workout = Workout(
            id=1,
            user_id="00000000-0000-0000-0000-000000000000",
            exercise_name="Pull-Up / Chin-Up",
            video_storage_path=self.video_path
        )
        self.mock_log = BiomechanicsLog(
            id=1,
            workout_id=1,
            status="pending"
        )

        # Mock AsyncSession
        self.mock_db = AsyncMock()
        
        async def mock_execute(stmt):
            mock_res = MagicMock()
            if "biomechanics_logs" in str(stmt):
                mock_res.scalar_one_or_none.return_value = self.mock_log
            else:
                mock_res.scalar_one_or_none.return_value = self.mock_workout
            return mock_res

        self.mock_db.execute = AsyncMock(side_effect=mock_execute)
        self.mock_db.commit = AsyncMock()
        self.mock_db.close = AsyncMock()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    @patch("app.services.ml_pipeline.PoseExtractor")
    @patch("app.services.coach_agent.CoachAgent.generate_feedback")
    @patch("app.services.video_renderer.render_overlay_video")
    @patch("app.services.ml_pipeline.is_r2_configured", return_value=True)
    @patch("app.services.ml_pipeline.upload_file_to_r2", return_value="https://pub-r2.dev/mock_overlay.mp4")
    @patch("app.services.ml_pipeline.delete_r2_file")
    async def test_successful_two_phase_pipeline_flow(
        self, mock_del_r2, mock_up_r2, mock_is_r2, mock_render, mock_feedback, mock_pose_cls
    ):
        """Verifies pending -> processing -> metrics_ready -> completed lifecycle."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_video.return_value = _mock_frame_data(30)
        mock_pose_cls.return_value = mock_extractor

        mock_feedback.return_value = BiomechanicsFeedback(
            scorecard=[
                ScorecardTier(category="ROM Standardization", rating="Good", confidence="HIGH", note="Full lockout achieved.")
            ],
            camera_observations="Consistent vertical bar path observed.",
            actionable_cues=["Maintain elbow drive through the bottom."],
            measurement_limitations="Clean side angle tracking."
        )

        recorded_statuses = []

        async def capture_status_commits(*args, **kwargs):
            recorded_statuses.append(self.mock_log.status)
            return None

        self.mock_db.commit = AsyncMock(side_effect=capture_status_commits)

        # Run pipeline task
        await process_video_task(
            log_id=1,
            video_storage_path=self.video_path,
            db=self.mock_db,
            user_height_cm=178.0
        )

        # Expected progression: 'processing' -> 'metrics_ready' (Phase 1) -> 'completed' (Phase 2)
        self.assertIn("processing", recorded_statuses)
        self.assertIn("metrics_ready", recorded_statuses)
        self.assertEqual(recorded_statuses[-1], "completed")

        # Assert data population
        self.assertIsNotNone(self.mock_log.raw_timeseries_data)
        self.assertIsNotNone(self.mock_log.coach_feedback)
        self.assertEqual(self.mock_log.coach_feedback["scorecard"][0]["category"], "ROM Standardization")
        self.assertEqual(self.mock_log.overlay_video_url, "https://pub-r2.dev/mock_overlay.mp4")

    @patch("app.services.ml_pipeline.PoseExtractor")
    async def test_pipeline_failure_safely_marks_log_as_failed(self, mock_pose_cls):
        """Verifies that an unhandled extraction error transitions log status to 'failed'."""
        mock_extractor = MagicMock()
        mock_extractor.extract_from_video.side_effect = RuntimeError("Decoder hardware failure")
        mock_pose_cls.return_value = mock_extractor

        await process_video_task(
            log_id=1,
            video_storage_path=self.video_path,
            db=self.mock_db
        )

        self.assertEqual(self.mock_log.status, "failed")
        self.mock_db.commit.assert_called()


if __name__ == "__main__":
    unittest.main()
