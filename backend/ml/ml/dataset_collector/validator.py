"""
Quality Assurance and Landmark Validation for Collected Clips.

Verifies that downloaded clips are decodable, have sufficient resolution and frame rate,
and contain a tracked lifter performing genuine physical movement.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import os
import sys
import cv2
import numpy as np

_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.ml.dataset_collector.manifest import ClipEntry, DatasetManifest
from app.services.video_processor import PoseExtractor
from app.services.exercise_validator import validate_pose_quality, _elbow_flexion_series


@dataclass
class QualityCheckResult:
    clip_id: str
    is_valid: bool
    reason: Optional[str] = None
    fps: float = 0.0
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    pose_quality_ratio: float = 0.0
    max_elbow_travel_deg: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class VideoValidator:
    """Validates raw collected clips before adding them to training datasets."""

    def __init__(self, pose_extractor: Optional[PoseExtractor] = None):
        self.pose_extractor = pose_extractor

    def _get_extractor(self) -> PoseExtractor:
        if self.pose_extractor is None:
            # Use lite or full model for validation
            self.pose_extractor = PoseExtractor(model_complexity=1)
        return self.pose_extractor

    def validate_file(self, video_path: str, clip_id: str = "unknown") -> QualityCheckResult:
        """Runs technical and visual verification on a single video file."""
        if not os.path.exists(video_path):
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason="file_not_found"
            )

        if os.path.getsize(video_path) < 10000:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason="file_empty_or_truncated"
            )

        # 1. Technical Container & Codec Check
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason="video_unreadable_by_opencv"
            )

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        duration = total_frames / fps if fps > 0 else 0.0

        if width < 240 or height < 240:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"low_resolution ({width}x{height})",
                fps=fps, width=width, height=height, duration_s=round(duration, 2)
            )

        if fps < 10.0 or fps > 120.0:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"unsupported_fps ({fps:.1f})",
                fps=fps, width=width, height=height, duration_s=round(duration, 2)
            )

        if duration < 1.0:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"clip_too_short ({duration:.1f}s)",
                fps=fps, width=width, height=height, duration_s=round(duration, 2)
            )

        # 2. Extract Landmarks & Visual QA
        try:
            extractor = self._get_extractor()
            frame_data = extractor.extract_from_video(video_path)
        except Exception as e:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"pose_extraction_error: {e}",
                fps=fps, width=width, height=height, duration_s=round(duration, 2)
            )

        if not frame_data:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason="zero_frames_extracted",
                fps=fps, width=width, height=height, duration_s=round(duration, 2)
            )

        # Gate 1: Check human pose detection ratio
        quality = validate_pose_quality(frame_data)
        ratio = quality.get("details", {}).get("tracked_frame_ratio", 0.0)

        if not quality.get("valid", False):
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"low_pose_quality ({ratio*100:.1f}%)",
                fps=fps, width=width, height=height, duration_s=round(duration, 2),
                pose_quality_ratio=round(ratio, 3),
                details=quality.get("details", {})
            )

        # Gate 2: Check active elbow flexion travel (distinguishes lifting from stationary poses)
        flex_r = _elbow_flexion_series(frame_data, "r")
        flex_l = _elbow_flexion_series(frame_data, "l")
        ranges = []
        for f_arr in (flex_r, flex_l):
            valid_pts = f_arr[np.isfinite(f_arr)]
            if len(valid_pts) >= 5:
                ranges.append(float(np.percentile(valid_pts, 95) - np.percentile(valid_pts, 5)))
        max_travel = max(ranges) if ranges else 0.0

        if max_travel < 12.0:
            return QualityCheckResult(
                clip_id=clip_id,
                is_valid=False,
                reason=f"insufficient_motion (elbow travel {max_travel:.1f}° < 12°)",
                fps=fps, width=width, height=height, duration_s=round(duration, 2),
                pose_quality_ratio=round(ratio, 3),
                max_elbow_travel_deg=round(max_travel, 1),
                details={"max_travel_deg": max_travel}
            )

        return QualityCheckResult(
            clip_id=clip_id,
            is_valid=True,
            reason=None,
            fps=fps, width=width, height=height, duration_s=round(duration, 2),
            pose_quality_ratio=round(ratio, 3),
            max_elbow_travel_deg=round(max_travel, 1),
            details={"max_travel_deg": max_travel}
        )

    def verify_manifest(
        self,
        manifest: DatasetManifest,
        dataset_dir: str = "data/dataset",
        save_updates: bool = True
    ) -> List[QualityCheckResult]:
        """Runs quality verification on all downloaded clips for a manifest."""
        results = []
        verified_count = 0

        for entry in manifest.entries:
            safe_exercise = entry.exercise.replace("/", "_").replace(" ", "_").lower()
            clip_path = os.path.join(dataset_dir, safe_exercise, entry.local_filename or f"{entry.clip_id}.mp4")

            res = self.validate_file(clip_path, clip_id=entry.clip_id)
            results.append(res)

            entry.verified = res.is_valid
            if res.is_valid:
                verified_count += 1
                print(f"[VALID] {entry.clip_id}: {res.width}x{res.height} @ {res.fps:.1f}fps, "
                      f"pose {res.pose_quality_ratio*100:.0f}%, travel {res.max_elbow_travel_deg:.1f}°")
            else:
                print(f"[REJECT] {entry.clip_id}: {res.reason}")

        print(f"\nManifest Verification: {verified_count}/{len(manifest.entries)} verified valid.")
        return results
