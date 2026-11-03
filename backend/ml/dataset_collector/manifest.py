"""
Dataset Manifest Management for FormAI.

Defines schemas and serialization for dataset manifests, with support for
YAML/CSV and strict lifter-isolated train/val/test splits to avoid data leakage.
"""
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
import os
import csv
import yaml
import random

SUPPORTED_EXERCISES = [
    "Pull-Up / Chin-Up",
    "Lat Pulldown",
    "Barbell Row",
    "Seated Cable Row",
    "Single-Arm Dumbbell Row",
]

FORM_LABELS = [
    "good_form",          # Standardized full ROM, minimal momentum, symmetrical
    "partial_rom",        # Incomplete chin over bar, short pulldown, or incomplete extension
    "torso_swing",        # Excessive body english, kipping, hip drive, lumbar hyperextension
    "asymmetrical_pull",  # One arm flares or reaches peak contraction prematurely
    "shrugged_shoulders", # Upper trap hiking at peak contraction
    "excessive_momentum", # High velocity jerk / drop without controlled eccentric
]

CAMERA_ANGLES = ["side", "front", "45_degree", "back", "unknown"]


def parse_timestamp(value: Any) -> float:
    """
    Parses various timestamp representations into float seconds.
    Examples:
      '00:15' -> 15.0
      '01:25.5' -> 85.5
      '01:02:03' -> 3723.0
      15 -> 15.0
      15.5 -> 15.5
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse timestamp: {value}")
    
    parts = value.strip().split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        else:
            raise ValueError(f"Invalid timestamp format: {value}")
    except ValueError as e:
        raise ValueError(f"Could not convert timestamp '{value}' to seconds: {e}")


def format_timestamp(seconds: float) -> str:
    """Formats float seconds as MM:SS.S or HH:MM:SS.S string."""
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:04.1f}"
    return f"{mins:02d}:{secs:04.1f}"


@dataclass
class ClipEntry:
    clip_id: str
    exercise: str
    form_label: str
    source_url: str
    start_time: float
    end_time: float
    lifter_id: str
    camera_angle: str = "unknown"
    split: str = "train"  # 'train', 'val', 'test'
    verified: bool = False
    notes: Optional[str] = ""
    local_filename: Optional[str] = None

    def __post_init__(self):
        self.start_time = parse_timestamp(self.start_time)
        self.end_time = parse_timestamp(self.end_time)
        if self.end_time <= self.start_time:
            raise ValueError(f"end_time ({self.end_time}) must be greater than start_time ({self.start_time})")
        if not self.local_filename:
            self.local_filename = f"{self.clip_id}.mp4"

    @property
    def duration_s(self) -> float:
        return round(self.end_time - self.start_time, 2)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["duration_s"] = self.duration_s
        return d


class DatasetManifest:
    """Manages collections of video clips and annotations."""

    def __init__(self, entries: Optional[List[ClipEntry]] = None):
        self.entries: List[ClipEntry] = entries or []

    def __len__(self) -> int:
        return len(self.entries)

    def add_entry(self, entry: ClipEntry, overwrite: bool = False):
        existing_idx = next((i for i, e in enumerate(self.entries) if e.clip_id == entry.clip_id), None)
        if existing_idx is not None:
            if overwrite:
                self.entries[existing_idx] = entry
            else:
                raise ValueError(f"Clip ID '{entry.clip_id}' already exists in manifest.")
        else:
            self.entries.append(entry)

    def get_entry(self, clip_id: str) -> Optional[ClipEntry]:
        for e in self.entries:
            if e.clip_id == clip_id:
                return e
        return None

    @classmethod
    def load_yaml(cls, filepath: str) -> "DatasetManifest":
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Manifest file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        entries = []
        raw_entries = data.get("clips", []) if isinstance(data, dict) else (data or [])
        for item in raw_entries:
            entries.append(ClipEntry(
                clip_id=item["clip_id"],
                exercise=item["exercise"],
                form_label=item.get("form_label", "good_form"),
                source_url=item["source_url"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                lifter_id=item["lifter_id"],
                camera_angle=item.get("camera_angle", "unknown"),
                split=item.get("split", "train"),
                verified=item.get("verified", False),
                notes=item.get("notes", ""),
                local_filename=item.get("local_filename")
            ))
        return cls(entries=entries)

    def save_yaml(self, filepath: str):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        raw_list = [e.to_dict() for e in self.entries]
        data = {
            "version": "1.0",
            "total_clips": len(self.entries),
            "clips": raw_list
        }
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load_csv(cls, filepath: str) -> "DatasetManifest":
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Manifest CSV not found: {filepath}")
        entries = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(ClipEntry(
                    clip_id=row["clip_id"],
                    exercise=row["exercise"],
                    form_label=row.get("form_label", "good_form"),
                    source_url=row["source_url"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    lifter_id=row["lifter_id"],
                    camera_angle=row.get("camera_angle", "unknown"),
                    split=row.get("split", "train"),
                    verified=str(row.get("verified", "false")).lower() in ("true", "1", "yes"),
                    notes=row.get("notes", ""),
                    local_filename=row.get("local_filename")
                ))
        return cls(entries=entries)

    def save_csv(self, filepath: str):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        fieldnames = [
            "clip_id", "exercise", "form_label", "lifter_id", "camera_angle",
            "start_time", "end_time", "duration_s", "split", "verified",
            "source_url", "local_filename", "notes"
        ]
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for e in self.entries:
                writer.writerow(e.to_dict())

    def assign_splits_by_lifter(
        self,
        val_ratio: float = 0.20,
        test_ratio: float = 0.10,
        seed: int = 42
    ) -> Dict[str, int]:
        """
        Partitions clips into 'train', 'val', and 'test' splits using GroupSplit by lifter_id.
        Guarantees that all clips from any single lifter belong exclusively to one split,
        preventing identity/environment data leakage.
        """
        if not self.entries:
            return {"train": 0, "val": 0, "test": 0}

        # Group clips by lifter
        lifters: Dict[str, List[ClipEntry]] = {}
        for e in self.entries:
            lifters.setdefault(e.lifter_id, []).append(e)

        unique_lifters = sorted(list(lifters.keys()))
        rng = random.Random(seed)
        rng.shuffle(unique_lifters)

        total_clips = len(self.entries)
        target_val = int(round(total_clips * val_ratio))
        target_test = int(round(total_clips * test_ratio))

        val_clips, test_clips = 0, 0
        lifter_to_split: Dict[str, str] = {}

        # If very few lifters, assign at least 1 to val / test if possible
        for lifter in unique_lifters:
            count = len(lifters[lifter])
            if test_clips < target_test and len(unique_lifters) >= 3:
                lifter_to_split[lifter] = "test"
                test_clips += count
            elif val_clips < target_val and len(unique_lifters) >= 2:
                lifter_to_split[lifter] = "val"
                val_clips += count
            else:
                lifter_to_split[lifter] = "train"

        # Apply split to each clip
        counts = {"train": 0, "val": 0, "test": 0}
        for e in self.entries:
            s = lifter_to_split.get(e.lifter_id, "train")
            e.split = s
            counts[s] += 1

        return counts

    def get_summary(self) -> Dict[str, Any]:
        """Calculates balance and distribution metrics across the dataset."""
        exercises: Dict[str, int] = {}
        labels: Dict[str, int] = {}
        splits: Dict[str, int] = {"train": 0, "val": 0, "test": 0}
        lifters: Dict[str, int] = {}
        verified_count = 0
        total_duration = 0.0

        for e in self.entries:
            exercises[e.exercise] = exercises.get(e.exercise, 0) + 1
            labels[e.form_label] = labels.get(e.form_label, 0) + 1
            splits[e.split] = splits.get(e.split, 0) + 1
            lifters[e.lifter_id] = lifters.get(e.lifter_id, 0) + 1
            if e.verified:
                verified_count += 1
            total_duration += e.duration_s

        return {
            "total_clips": len(self.entries),
            "total_duration_minutes": round(total_duration / 60.0, 1),
            "unique_lifters": len(lifters),
            "verified_clips": verified_count,
            "exercises": exercises,
            "form_labels": labels,
            "splits": splits,
            "top_lifters": sorted(lifters.items(), key=lambda x: x[1], reverse=True)[:5],
        }
