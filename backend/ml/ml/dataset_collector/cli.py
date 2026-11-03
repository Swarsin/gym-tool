"""
FormAI Dataset Collector CLI.

Command-line interface to curate, download, verify, partition, and extract features
from exercise video datasets.
"""
import argparse
import os
import sys

_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from backend.ml.dataset_collector.manifest import (
    ClipEntry,
    DatasetManifest,
    SUPPORTED_EXERCISES,
    FORM_LABELS,
    CAMERA_ANGLES,
)
from backend.ml.dataset_collector.downloader import VideoDownloader
from backend.ml.dataset_collector.validator import VideoValidator
from backend.ml.dataset_collector.features import DatasetFeatureExtractor


DEFAULT_MANIFEST_PATH = "data/manifests/starter_dataset.yaml"
DEFAULT_DATASET_DIR = "data/dataset"


def cmd_add(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if os.path.exists(manifest_path):
        manifest = DatasetManifest.load_yaml(manifest_path)
    else:
        manifest = DatasetManifest()

    entry = ClipEntry(
        clip_id=args.clip_id,
        exercise=args.exercise,
        form_label=args.label,
        source_url=args.url,
        start_time=args.start,
        end_time=args.end,
        lifter_id=args.lifter,
        camera_angle=args.angle,
        notes=args.notes or "",
    )

    manifest.add_entry(entry, overwrite=args.overwrite)
    manifest.save_yaml(manifest_path)
    print(f"Successfully added '{entry.clip_id}' to {manifest_path} (Total clips: {len(manifest)}).")


def cmd_stats(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest '{manifest_path}' does not exist.")
        sys.exit(1)

    manifest = DatasetManifest.load_yaml(manifest_path)
    summary = manifest.get_summary()

    print("\n================ FormAI Dataset Summary ================")
    print(f"Manifest File:             {manifest_path}")
    print(f"Total Clips:               {summary['total_clips']}")
    print(f"Total Duration:            {summary['total_duration_minutes']} minutes")
    print(f"Unique Lifters:            {summary['unique_lifters']}")
    print(f"Verified Clips:            {summary['verified_clips']} / {summary['total_clips']}")
    print("\n--- Exercise Breakdown ---")
    for ex, cnt in sorted(summary["exercises"].items(), key=lambda x: -x[1]):
        pct = (cnt / summary['total_clips']) * 100 if summary['total_clips'] else 0
        print(f"  * {ex:<28}: {cnt:>3} ({pct:>4.1f}%)")

    print("\n--- Form Flaw / Quality Labels ---")
    for lbl, cnt in sorted(summary["form_labels"].items(), key=lambda x: -x[1]):
        pct = (cnt / summary['total_clips']) * 100 if summary['total_clips'] else 0
        print(f"  * {lbl:<28}: {cnt:>3} ({pct:>4.1f}%)")

    print("\n--- Split Allocation (by lifter) ---")
    for s, cnt in summary["splits"].items():
        pct = (cnt / summary['total_clips']) * 100 if summary['total_clips'] else 0
        print(f"  * {s:<10}: {cnt:>3} clips ({pct:>4.1f}%)")

    print("\n--- Top Lifters ---")
    for lifter, cnt in summary["top_lifters"]:
        print(f"  * {lifter:<20}: {cnt} clips")
    print("========================================================\n")


def cmd_download(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest '{manifest_path}' does not exist.")
        sys.exit(1)

    manifest = DatasetManifest.load_yaml(manifest_path)
    downloader = VideoDownloader(output_dir=args.out_dir or DEFAULT_DATASET_DIR)
    results = downloader.download_manifest(
        manifest,
        overwrite=args.overwrite,
        limit=args.limit
    )


def cmd_verify(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest '{manifest_path}' does not exist.")
        sys.exit(1)

    manifest = DatasetManifest.load_yaml(manifest_path)
    validator = VideoValidator()
    validator.verify_manifest(
        manifest,
        dataset_dir=args.dataset_dir or DEFAULT_DATASET_DIR,
        save_updates=True
    )
    manifest.save_yaml(manifest_path)
    print(f"Updated verification flags in {manifest_path}.")


def cmd_split(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest '{manifest_path}' does not exist.")
        sys.exit(1)

    manifest = DatasetManifest.load_yaml(manifest_path)
    counts = manifest.assign_splits_by_lifter(
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed
    )
    manifest.save_yaml(manifest_path)
    print(f"Re-partitioned splits strictly by lifter (val_ratio={args.val_ratio}, test_ratio={args.test_ratio}):")
    print(f"  Train: {counts['train']} | Val: {counts['val']} | Test: {counts['test']}")


def cmd_extract(args):
    manifest_path = args.manifest or DEFAULT_MANIFEST_PATH
    if not os.path.exists(manifest_path):
        print(f"Error: Manifest '{manifest_path}' does not exist.")
        sys.exit(1)

    manifest = DatasetManifest.load_yaml(manifest_path)
    extractor = DatasetFeatureExtractor(
        dataset_dir=args.dataset_dir or DEFAULT_DATASET_DIR,
        output_dir=args.out_dir or "data/ml_ready"
    )
    csv_path, npz_path = extractor.extract_from_manifest(manifest)
    print(f"\nExtraction complete!\nTabular CSV: {csv_path}\nSequences NPZ: {npz_path}")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m backend.ml.dataset_collector.cli",
        description="FormAI Dataset Ingestion, Quality Assurance & ML Feature Extraction CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: add
    p_add = subparsers.add_parser("add", help="Add a new clip to manifest")
    p_add.add_argument("--clip-id", required=True, help="Unique identifier for the clip")
    p_add.add_argument("--exercise", required=True, choices=SUPPORTED_EXERCISES, help="Exercise movement name")
    p_add.add_argument("--label", required=True, choices=FORM_LABELS, help="Form flaw or quality label")
    p_add.add_argument("--url", required=True, help="YouTube, direct MP4, or local file path")
    p_add.add_argument("--start", required=True, help="Start time in seconds or MM:SS")
    p_add.add_argument("--end", required=True, help="End time in seconds or MM:SS")
    p_add.add_argument("--lifter", required=True, help="Unique lifter identifier for grouped splitting")
    p_add.add_argument("--angle", choices=CAMERA_ANGLES, default="unknown", help="Camera viewpoint")
    p_add.add_argument("--notes", default="", help="Optional context or flaw description")
    p_add.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_add.add_argument("--overwrite", action="store_true", help="Overwrite if clip-id already exists")
    p_add.set_defaults(func=cmd_add)

    # Subcommand: stats
    p_stats = subparsers.add_parser("stats", help="Display dataset balance and split statistics")
    p_stats.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_stats.set_defaults(func=cmd_stats)

    # Subcommand: download
    p_dl = subparsers.add_parser("download", help="Batch download and trim clips in manifest")
    p_dl.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_dl.add_argument("--out-dir", default=DEFAULT_DATASET_DIR, help="Destination folder for downloaded clips")
    p_dl.add_argument("--limit", type=int, default=None, help="Limit number of clips to download")
    p_dl.add_argument("--overwrite", action="store_true", help="Re-download clips even if already present")
    p_dl.set_defaults(func=cmd_download)

    # Subcommand: verify
    p_ver = subparsers.add_parser("verify", help="Run CV & pose quality check on downloaded clips")
    p_ver.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_ver.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="Directory containing clips")
    p_ver.set_defaults(func=cmd_verify)

    # Subcommand: split
    p_split = subparsers.add_parser("split", help="Assign train/val/test splits grouped by lifter")
    p_split.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_split.add_argument("--val-ratio", type=float, default=0.20, help="Fraction of clips for validation")
    p_split.add_argument("--test-ratio", type=float, default=0.10, help="Fraction of clips for test")
    p_split.add_argument("--seed", type=int, default=42, help="Random seed for deterministic split")
    p_split.set_defaults(func=cmd_split)

    # Subcommand: extract
    p_ext = subparsers.add_parser("extract", help="Extract tabular features and 3D sequence tensors")
    p_ext.add_argument("--manifest", default=DEFAULT_MANIFEST_PATH, help="Path to manifest file")
    p_ext.add_argument("--dataset-dir", default=DEFAULT_DATASET_DIR, help="Directory containing clips")
    p_ext.add_argument("--out-dir", default="data/ml_ready", help="Directory for exported CSV and NPZ")
    p_ext.set_defaults(func=cmd_extract)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
