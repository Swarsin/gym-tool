import cv2
import math
import urllib.request
import os
import time
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from typing import List, Dict, Any, Optional, Tuple

# Allow container-specific tuning without assuming fewer threads are faster.
# Configure once, before any processing threads are started.
if os.getenv("OPENCV_NUM_THREADS") is not None:
    _opencv_threads = int(os.environ["OPENCV_NUM_THREADS"])
    if _opencv_threads < 1:
        raise ValueError("OPENCV_NUM_THREADS must be a positive integer")
    cv2.setNumThreads(_opencv_threads)


class OneEuroFilter:
    """
    Adaptive 1€ (OneEuro) Filter for low-latency, jitter-free signal smoothing.
    Reference: Casiez, Roussel, Vogel (CHI 2012) - https://gery.casiez.net/1euro/
    """
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev: Optional[np.ndarray] = None
        self.dx_prev: Optional[np.ndarray] = None
        self.t_prev: Optional[float] = None

    def _alpha(self, dt: float, cutoff: np.ndarray) -> np.ndarray:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: np.ndarray, t: float) -> np.ndarray:
        if self.t_prev is None or self.x_prev is None:
            self.x_prev = np.array(x, dtype=float)
            self.dx_prev = np.zeros_like(self.x_prev)
            self.t_prev = float(t)
            return np.copy(self.x_prev)

        dt = t - self.t_prev
        if dt <= 0.0:
            dt = 1e-4

        # 1. Estimate derivative
        dx = (x - self.x_prev) / dt
        alpha_d = self._alpha(dt, np.full_like(dx, self.d_cutoff))
        dx_hat = alpha_d * dx + (1.0 - alpha_d) * self.dx_prev

        # 2. Adaptive cutoff frequency based on speed
        cutoff = self.min_cutoff + self.beta * np.abs(dx_hat)
        alpha = self._alpha(dt, cutoff)

        # 3. Filter position
        x_hat = alpha * x + (1.0 - alpha) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = float(t)
        return np.copy(x_hat)

    def reset(self):
        self.x_prev = None
        self.dx_prev = None
        self.t_prev = None


class PoseExtractor:
    """
    Handles OpenCV video ingestion and MediaPipe landmark extraction for biomechanical analysis.
    Uses MediaPipe Video Mode with explicit timestamps, dual 2D/3D World extraction,
    and a 3-state landmark pipeline (raw -> filtered -> display).
    """

    TARGET_LANDMARKS = {
        'shoulder_l': 11, 'shoulder_r': 12,
        'elbow_l': 13, 'elbow_r': 14,
        'wrist_l': 15, 'wrist_r': 16,
        'hip_l': 23, 'hip_r': 24,
        'knee_l': 25, 'knee_r': 26,
        'ankle_l': 27, 'ankle_r': 28
    }

    FILTER_CONFIG = {
        "image_landmarks": {"min_cutoff": 1.0, "beta": 0.007, "d_cutoff": 1.0},
        "world_landmarks": {"min_cutoff": 0.8, "beta": 0.04, "d_cutoff": 1.0},
    }

    MODEL_CONFIGS = {
        0: {
            "name": "pose_landmarker_lite.task",
            "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        },
        1: {
            "name": "pose_landmarker_full.task",
            "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
        },
        2: {
            "name": "pose_landmarker_heavy.task",
            "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task",
        },
    }

    def __init__(self, model_complexity: Optional[int] = None, target_fps: Optional[float] = None):
        target_fps = float(target_fps if target_fps is not None else os.getenv("MEDIAPIPE_TARGET_FPS", "30"))
        if not math.isfinite(target_fps) or not 1 <= target_fps <= 60:
            raise ValueError("MEDIAPIPE_TARGET_FPS must be between 1 and 60")
        self.target_fps = target_fps
        self.last_profile = {}
        if model_complexity is None:
            env_val = os.getenv("MEDIAPIPE_MODEL_COMPLEXITY", "1")
            try:
                model_complexity = int(env_val)
            except ValueError:
                model_complexity = 1

        cfg = self.MODEL_CONFIGS.get(model_complexity, self.MODEL_CONFIGS[1])
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.model_path = os.path.join(base_dir, cfg["name"])
        if not os.path.exists(self.model_path):
            print(f"Downloading MediaPipe Pose model ({cfg['name']})...")
            urllib.request.urlretrieve(cfg["url"], self.model_path)

    def _create_detector(self):
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            output_segmentation_masks=False,
            running_mode=vision.RunningMode.VIDEO
        )
        return vision.PoseLandmarker.create_from_options(options)

    def extract_from_video(self, video_path: str) -> List[Dict[str, Any]]:
        """
        Extracts 2D image landmarks and 3D world landmarks across frames with OneEuro filtering.
        Produces 3 landmark states: raw, filtered (for measurement), and display (interpolated for rendering).
        """
        # Fresh detector per video: VIDEO mode keeps tracking state and requires monotonic
        # timestamps, so reusing one across videos could leak the previous clip's pose into
        # the first frames of the next. It is always closed to release native resources.
        started = time.perf_counter()
        detector = self._create_detector()
        self.last_profile = {"model": os.path.basename(self.model_path), "target_fps": self.target_fps,
                             "detector_init_s": time.perf_counter() - started}
        try:
            return self._extract_with_detector(video_path, detector)
        finally:
            detector.close()
            self.last_profile["total_s"] = time.perf_counter() - started

    def _extract_with_detector(self, video_path: str, detector) -> List[Dict[str, Any]]:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Error opening video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or not math.isfinite(fps):
            fps = 30.0

        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        # Calculate proportional scale if resolution exceeds 720p to prevent OOM
        max_dim = max(orig_w, orig_h) if (orig_w > 0 and orig_h > 0) else 720
        target_max = 720
        scale = target_max / max_dim if max_dim > target_max else 1.0
        new_w = int(orig_w * scale) if orig_w > 0 else 720
        new_h = int(orig_h * scale) if orig_h > 0 else 720

        sample_fps = min(fps, self.target_fps)
        # Phone metadata can report 30.03 for a nominal 30 FPS clip. Keep every
        # frame near the target instead of dropping an isolated tracking frame.
        retain_all = fps <= self.target_fps * 1.005
        profile = self.last_profile
        profile.update(source_fps=fps, source_width=orig_w, source_height=orig_h,
                       opencv_threads=cv2.getNumThreads(), decode_s=0.0,
                       preprocess_s=0.0, inference_s=0.0, filtering_s=0.0)

        raw_frames = []
        frame_idx = 0
        read_idx = 0
        last_timestamp_ms = -1
        last_source_time = -1.0
        next_sample_time = 0.0

        # OneEuro filters per tracked landmark
        cfg_2d = self.FILTER_CONFIG["image_landmarks"]
        cfg_3d = self.FILTER_CONFIG["world_landmarks"]
        filters_2d = {name: OneEuroFilter(**cfg_2d) for name in self.TARGET_LANDMARKS}
        filters_3d = {name: OneEuroFilter(**cfg_3d) for name in self.TARGET_LANDMARKS}

        try:
            while cap.isOpened():
                t0 = time.perf_counter()
                ret = cap.grab()
                profile["decode_s"] += time.perf_counter() - t0
                if not ret:
                    break
                source_idx = read_idx
                read_idx += 1
                # Prefer presentation time (including variable-frame-rate sources).
                source_time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                if not math.isfinite(source_time) or source_time < 0 or source_time <= last_source_time:
                    source_time = max(source_idx / fps, last_source_time + 1.0 / fps)
                last_source_time = source_time
                if not retain_all and source_time + 1e-7 < next_sample_time:
                    continue
                next_sample_time = (math.floor(source_time * sample_fps + 1e-7) + 1) / sample_fps
                t0 = time.perf_counter()
                ret, frame = cap.retrieve()
                profile["decode_s"] += time.perf_counter() - t0
                if not ret:
                    raise ValueError(f"Cannot retrieve video frame {source_idx}")
                timestamp_s = source_time
                timestamp_ms = max(last_timestamp_ms + 1, int(round(timestamp_s * 1000)))
                last_timestamp_ms = timestamp_ms
                t0 = time.perf_counter()

                if scale < 1.0:
                    frame_resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                else:
                    frame_resized = frame

                image_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
                profile["preprocess_s"] += time.perf_counter() - t0
                t0 = time.perf_counter()
                detection_result = detector.detect_for_video(mp_image, timestamp_ms)
                profile["inference_s"] += time.perf_counter() - t0
                t0 = time.perf_counter()

                raw_dict = {}
                filtered_dict = {}
                world_dict = {}
                confidence_dict = {}

                if detection_result.pose_landmarks:
                    landmarks_2d = detection_result.pose_landmarks[0]
                    landmarks_3d = detection_result.pose_world_landmarks[0] if detection_result.pose_world_landmarks else None

                    for name, idx in self.TARGET_LANDMARKS.items():
                        lm2 = landmarks_2d[idx]
                        vis = getattr(lm2, 'visibility', None)
                        pres = getattr(lm2, 'presence', None)
                        conf = float(min(1.0 if vis is None else vis, 1.0 if pres is None else pres))
                        confidence_dict[name] = conf

                        raw_coord = np.array([lm2.x, lm2.y, lm2.z], dtype=float)
                        raw_dict[name] = [float(lm2.x), float(lm2.y), float(lm2.z), conf]

                        if conf >= 0.35:
                            filt_coord = filters_2d[name].filter(raw_coord, timestamp_s)
                            filtered_dict[name] = [float(filt_coord[0]), float(filt_coord[1]), float(filt_coord[2]), conf]
                        else:
                            filtered_dict[name] = None

                        if landmarks_3d and conf >= 0.35:
                            lm3 = landmarks_3d[idx]
                            raw_world = np.array([lm3.x, lm3.y, lm3.z], dtype=float)
                            filt_world = filters_3d[name].filter(raw_world, timestamp_s)
                            world_dict[name] = [float(filt_world[0]), float(filt_world[1]), float(filt_world[2]), conf]
                        else:
                            world_dict[name] = None

                raw_frames.append({
                    "frame_index": frame_idx,
                    "source_frame_index": source_idx,
                    "sample_fps": sample_fps,
                    "timestamp_ms": timestamp_ms,
                    "timestamp_s": timestamp_s,
                    "raw_landmarks": raw_dict,
                    "filtered_landmarks": filtered_dict,
                    "world_landmarks": world_dict,
                    "confidences": confidence_dict,
                    "landmarks": {k: v for k, v in filtered_dict.items() if v is not None}
                })
                frame_idx += 1
                profile["filtering_s"] += time.perf_counter() - t0
        finally:
            cap.release()

        source_end = max(0.0, last_source_time + 1.0 / fps)
        for i, fd in enumerate(raw_frames):
            end = raw_frames[i + 1]["timestamp_s"] if i + 1 < len(raw_frames) else source_end
            fd["duration_s"] = end - fd["timestamp_s"]
        profile.update(source_frames=read_idx, inference_frames=len(raw_frames), source_duration_s=source_end,
                       sampling_fps=len(raw_frames) / source_end if source_end else 0.0)

        # Generate display_landmarks: forward/backward temporal linear interpolation across missing frames
        # strictly for skeleton rendering (never used for kinematic measurements)
        t0 = time.perf_counter()
        frame_data = self._build_display_landmarks(raw_frames)
        profile["display_interpolation_s"] = time.perf_counter() - t0
        return frame_data

    def _build_display_landmarks(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Creates display_landmarks by interpolating temporary occlusions exclusively for visual rendering.
        """
        n_frames = len(frames)
        if n_frames == 0:
            return frames

        for name in self.TARGET_LANDMARKS:
            # Collect frame indices where joint is present
            valid_indices = [
                i for i in range(n_frames)
                if frames[i]["filtered_landmarks"].get(name) is not None
            ]

            if not valid_indices:
                continue

            valid_cursor = 0
            for i in range(n_frames):
                if frames[i]["filtered_landmarks"].get(name) is not None:
                    # Point already valid
                    if "display_landmarks" not in frames[i]:
                        frames[i]["display_landmarks"] = {}
                    frames[i]["display_landmarks"][name] = frames[i]["filtered_landmarks"][name]
                else:
                    # Interpolate from nearest left and right valid frames
                    while valid_cursor < len(valid_indices) and valid_indices[valid_cursor] < i:
                        valid_cursor += 1
                    left_idx = valid_indices[valid_cursor - 1] if valid_cursor else None
                    right_idx = valid_indices[valid_cursor] if valid_cursor < len(valid_indices) else None

                    if left_idx is not None and right_idx is not None:
                        t = (frames[i]["timestamp_s"] - frames[left_idx]["timestamp_s"]) / (
                            frames[right_idx]["timestamp_s"] - frames[left_idx]["timestamp_s"])
                        p_left = np.array(frames[left_idx]["filtered_landmarks"][name][:3])
                        p_right = np.array(frames[right_idx]["filtered_landmarks"][name][:3])
                        interp = (1.0 - t) * p_left + t * p_right
                        if "display_landmarks" not in frames[i]:
                            frames[i]["display_landmarks"] = {}
                        frames[i]["display_landmarks"][name] = [float(interp[0]), float(interp[1]), float(interp[2]), 0.0]
                    elif left_idx is not None:
                        if "display_landmarks" not in frames[i]:
                            frames[i]["display_landmarks"] = {}
                        frames[i]["display_landmarks"][name] = frames[left_idx]["filtered_landmarks"][name]
                    elif right_idx is not None:
                        if "display_landmarks" not in frames[i]:
                            frames[i]["display_landmarks"] = {}
                        frames[i]["display_landmarks"][name] = frames[right_idx]["filtered_landmarks"][name]

        return frames
