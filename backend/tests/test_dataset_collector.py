"""
Tests for Dataset Collector, Manifest Management, and Quality Assurance.
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from backend.ml.dataset_collector.manifest import (
    ClipEntry,
    DatasetManifest,
    parse_timestamp,
    format_timestamp,
)
from backend.ml.dataset_collector.downloader import VideoDownloader
from backend.ml.dataset_collector.validator import VideoValidator, QualityCheckResult
from backend.ml.dataset_collector.features import resample_sequence


class TestDatasetCollector(unittest.TestCase):

    def test_parse_and_format_timestamps(self):
        self.assertEqual(parse_timestamp("00:15"), 15.0)
        self.assertEqual(parse_timestamp("01:25.5"), 85.5)
        self.assertEqual(parse_timestamp("01:00:00"), 3600.0)
        self.assertEqual(parse_timestamp(42), 42.0)
        self.assertEqual(parse_timestamp(12.3), 12.3)

        self.assertEqual(format_timestamp(15.0), "00:15.0")
        self.assertEqual(format_timestamp(85.5), "01:25.5")
        self.assertEqual(format_timestamp(3605.0), "01:00:05.0")

        with self.assertRaises(ValueError):
            parse_timestamp("invalid:time:format:extra")

    def test_clip_entry_duration_and_validation(self):
        entry = ClipEntry(
            clip_id="test_01",
            exercise="Pull-Up / Chin-Up",
            form_label="good_form",
            source_url="https://youtube.com/watch?v=123",
            start_time="00:10",
            end_time="00:25",
            lifter_id="lifter_1",
            camera_angle="side"
        )
        self.assertEqual(entry.start_time, 10.0)
        self.assertEqual(entry.end_time, 25.0)
        self.assertEqual(entry.duration_s, 15.0)
        self.assertEqual(entry.local_filename, "test_01.mp4")

        # Inverted timestamps should raise ValueError
        with self.assertRaises(ValueError):
            ClipEntry(
                clip_id="bad_01",
                exercise="Lat Pulldown",
                form_label="partial_rom",
                source_url="test.mp4",
                start_time=20.0,
                end_time=10.0,
                lifter_id="lifter_1"
            )

    def test_manifest_yaml_and_csv_serialization(self):
        entry1 = ClipEntry(
            clip_id="c1",
            exercise="Pull-Up / Chin-Up",
            form_label="good_form",
            source_url="video1.mp4",
            start_time=0.0,
            end_time=10.0,
            lifter_id="lifter_a"
        )
        entry2 = ClipEntry(
            clip_id="c2",
            exercise="Lat Pulldown",
            form_label="torso_swing",
            source_url="video2.mp4",
            start_time=5.0,
            end_time=15.0,
            lifter_id="lifter_b"
        )
        manifest = DatasetManifest(entries=[entry1, entry2])

        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = os.path.join(tmpdir, "test_manifest.yaml")
            csv_path = os.path.join(tmpdir, "test_manifest.csv")

            # YAML Roundtrip
            manifest.save_yaml(yaml_path)
            loaded_yaml = DatasetManifest.load_yaml(yaml_path)
            self.assertEqual(len(loaded_yaml), 2)
            self.assertEqual(loaded_yaml.entries[0].clip_id, "c1")
            self.assertEqual(loaded_yaml.entries[1].form_label, "torso_swing")

            # CSV Roundtrip
            manifest.save_csv(csv_path)
            loaded_csv = DatasetManifest.load_csv(csv_path)
            self.assertEqual(len(loaded_csv), 2)
            self.assertEqual(loaded_csv.entries[0].clip_id, "c1")
            self.assertEqual(loaded_csv.entries[1].exercise, "Lat Pulldown")

    def test_grouped_split_strictly_isolates_lifters(self):
        # 9 clips across 3 lifters (3 clips each)
        entries = []
        for lifter in ["lifter_alpha", "lifter_beta", "lifter_gamma"]:
            for i in range(3):
                entries.append(ClipEntry(
                    clip_id=f"{lifter}_{i}",
                    exercise="Barbell Row",
                    form_label="good_form",
                    source_url=f"{lifter}_{i}.mp4",
                    start_time=0.0,
                    end_time=10.0,
                    lifter_id=lifter
                ))
        manifest = DatasetManifest(entries=entries)

        counts = manifest.assign_splits_by_lifter(val_ratio=0.33, test_ratio=0.33, seed=123)

        # Verify that all clips for each lifter belong to exactly ONE split
        lifter_splits = {}
        for e in manifest.entries:
            if e.lifter_id in lifter_splits:
                self.assertEqual(
                    e.split,
                    lifter_splits[e.lifter_id],
                    f"Lifter {e.lifter_id} leaked across multiple splits!"
                )
            else:
                lifter_splits[e.lifter_id] = e.split

        # All 3 lifters assigned
        self.assertEqual(len(lifter_splits), 3)

    def test_resample_sequence(self):
        import numpy as np
        # Original sequence: 10 frames with 3 features
        orig = np.ones((10, 3), dtype=np.float32) * 5.0
        resampled = resample_sequence(orig, target_length=30)
        self.assertEqual(resampled.shape, (30, 3))
        self.assertTrue(np.allclose(resampled, 5.0))

    def test_validator_detects_missing_file(self):
        validator = VideoValidator()
        result = validator.validate_file("non_existent_file_path.mp4", clip_id="missing_01")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "file_not_found")


if __name__ == "__main__":
    unittest.main()
