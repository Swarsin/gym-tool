"""
Feature and Biomechanics Sequence Extractor for Training Sets.

Extracts tabular biomechanical features (velocities, ROM, tempo, asymmetry) and
normalized 3D landmark temporal sequences from collected clips to create training datasets.
"""
import os
import sys
import csv
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.ml.dataset_collector.manifest import ClipEntry, DatasetManifest
from app.services.video_processor import PoseExtractor
from app.services.video_timing import sampling_fps
from app.services.biomechanics import analyze_set


# Key upper body landmarks used for sequence modeling
REPRESENTATIVE_JOINTS = [
    "shoulder_l", "shoulder_r",
    "elbow_l", "elbow_r",
    "wrist_l", "wrist_r",
    "hip_l", "hip_r",
]


def resample_sequence(sequence: np.ndarray, target_length: int = 30) -> np.ndarray:
    """
    Interpolates a sequence of shape (T, D) to (target_length, D) using linear interpolation.
    Enables uniform tensor inputs for neural network models.
    """
    t_orig = len(sequence)
    if t_orig == 0:
        return np.zeros((target_length, sequence.shape[1] if sequence.ndim > 1 else 1), dtype=np.float32)
    if t_orig == target_length:
        return sequence.astype(np.float32)

    x_orig = np.linspace(0, 1, t_orig)
    x_target = np.linspace(0, 1, target_length)

    resampled = np.zeros((target_length, sequence.shape[1]), dtype=np.float32)
    for dim in range(sequence.shape[1]):
        resampled[:, dim] = np.interp(x_target, x_orig, sequence[:, dim])
    return resampled


class DatasetFeatureExtractor:
    """Extracts ML-ready tabular features and tensors from verified video collections."""

    def __init__(self, dataset_dir: str = "data/dataset", output_dir: str = "data/ml_ready"):
        self.dataset_dir = dataset_dir
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.pose_extractor = PoseExtractor(model_complexity=1)

    def extract_from_manifest(
        self,
        manifest: DatasetManifest,
        target_seq_len: int = 30
    ) -> Tuple[str, str]:
        """
        Processes all verified clips in the manifest.
        Returns paths to (csv_path, npz_path).
        """
        tabular_rows: List[Dict[str, Any]] = []
        sequence_tensors: List[np.ndarray] = []
        y_exercise: List[str] = []
        y_form_label: List[str] = []
        clip_ids: List[str] = []
        lifter_ids: List[str] = []
        splits: List[str] = []

        total = len(manifest.entries)
        print(f"\nExtracting biomechanical features from {total} clips...")

        for idx, entry in enumerate(manifest.entries, 1):
            safe_exercise = entry.exercise.replace("/", "_").replace(" ", "_").lower()
            video_path = os.path.join(self.dataset_dir, safe_exercise, entry.local_filename or f"{entry.clip_id}.mp4")

            if not os.path.exists(video_path):
                print(f"[{idx}/{total}] Skipping missing file: {video_path}")
                continue

            try:
                frame_data = self.pose_extractor.extract_from_video(video_path)
                if not frame_data:
                    continue

                fps = sampling_fps(frame_data)
                set_metrics = analyze_set(frame_data, fps=fps, exercise_name=entry.exercise)
                reps = set_metrics.get("reps", [])

                if not reps:
                    # If no discrete rep boundaries detected, use full set as 1 sequence
                    rep_start_frame = 0
                    rep_end_frame = len(frame_data) - 1
                    reps = [{
                        "rep_number": 1,
                        "start_frame": rep_start_frame,
                        "end_frame": rep_end_frame,
                        "elbow_rom_deg": set_metrics.get("max_rom_overall_deg", 0.0),
                        "concentric_mean_velocity_mps": set_metrics.get("avg_concentric_velocity_mps", 0.0),
                        "concentric_peak_velocity_mps": set_metrics.get("peak_concentric_velocity_mps", 0.0),
                        "concentric_duration_s": round(len(frame_data) / 60.0, 2),
                        "eccentric_duration_s": round(len(frame_data) / 60.0, 2),
                        "flare_delta_deg": set_metrics.get("asymmetry_analysis", {}).get("avg_flare_delta_deg", 0.0),
                    }]

                for rep in reps:
                    start_f = rep.get("start_frame", 0)
                    end_f = rep.get("end_frame", len(frame_data) - 1)
                    if end_f <= start_f:
                        continue

                    # 1. Build tabular row
                    row = {
                        "clip_id": entry.clip_id,
                        "exercise": entry.exercise,
                        "form_label": entry.form_label,
                        "lifter_id": entry.lifter_id,
                        "split": entry.split,
                        "camera_angle": entry.camera_angle,
                        "rep_number": rep.get("rep_number", 1),
                        "rom_deg": round(float(rep.get("elbow_rom_deg", 0.0)), 2),
                        "concentric_mean_velocity_mps": round(float(rep.get("concentric_mean_velocity_mps", 0.0)), 3),
                        "concentric_peak_velocity_mps": round(float(rep.get("concentric_peak_velocity_mps", 0.0)), 3),
                        "concentric_sec": round(float(rep.get("concentric_duration_s", 0.0)), 2),
                        "eccentric_sec": round(float(rep.get("eccentric_duration_s", 0.0)), 2),
                        "flare_delta_deg": round(float(rep.get("flare_delta_deg", 0.0)), 2),
                        "overall_symmetry_score": round(float(set_metrics.get("asymmetry_analysis", {}).get("overall_symmetry_score", 100)), 1),
                    }
                    tabular_rows.append(row)

                    # 2. Build 3D normalized sequence tensor
                    rep_frames = frame_data[start_f:end_f + 1]
                    frame_features = []
                    for fd in rep_frames:
                        world = fd.get("world_landmarks", {}) or {}
                        # Extract coordinates (x, y, z) for 8 joints -> 24 features per frame
                        coords = []
                        # Reference center point: mid-shoulder
                        s_r = world.get("shoulder_r")
                        s_r_coords = s_r[:3] if s_r else [0.0, 0.0, 0.0]
                        s_l = world.get("shoulder_l")
                        s_l_coords = s_l[:3] if s_l else [0.0, 0.0, 0.0]
                        cx = (s_r_coords[0] + s_l_coords[0]) / 2.0
                        cy = (s_r_coords[1] + s_l_coords[1]) / 2.0
                        cz = (s_r_coords[2] + s_l_coords[2]) / 2.0

                        for joint in REPRESENTATIVE_JOINTS:
                            j_coord = world.get(joint)
                            if j_coord and len(j_coord) >= 3:
                                # Relative to body center
                                coords.extend([j_coord[0] - cx, j_coord[1] - cy, j_coord[2] - cz])
                            else:
                                coords.extend([0.0, 0.0, 0.0])
                        frame_features.append(coords)

                    raw_seq = np.array(frame_features, dtype=np.float32)
                    resampled = resample_sequence(raw_seq, target_length=target_seq_len)

                    sequence_tensors.append(resampled)
                    y_exercise.append(entry.exercise)
                    y_form_label.append(entry.form_label)
                    clip_ids.append(entry.clip_id)
                    lifter_ids.append(entry.lifter_id)
                    splits.append(entry.split)

                print(f"[{idx}/{total}] Extracted {len(reps)} reps from {entry.clip_id}")

            except Exception as e:
                print(f"[{idx}/{total}] Failed extracting features for {entry.clip_id}: {e}")

        # Save CSV tabular dataset
        csv_path = os.path.join(self.output_dir, "dataset_features.csv")
        if tabular_rows:
            fieldnames = list(tabular_rows[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(tabular_rows)
            print(f"\nSaved tabular dataset ({len(tabular_rows)} reps) to: {csv_path}")

        # Save NPZ sequence dataset
        npz_path = os.path.join(self.output_dir, "dataset_sequences.npz")
        if sequence_tensors:
            X_arr = np.array(sequence_tensors, dtype=np.float32)
            np.savez_compressed(
                npz_path,
                X=X_arr,
                y_exercise=np.array(y_exercise),
                y_form_label=np.array(y_form_label),
                clip_ids=np.array(clip_ids),
                lifter_ids=np.array(lifter_ids),
                splits=np.array(splits)
            )
            print(f"Saved tensor dataset (shape: {X_arr.shape}) to: {npz_path}")

        return csv_path, npz_path
