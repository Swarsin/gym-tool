"""Compare browser-trimmed clips with the existing server FFmpeg trimming path.

First run Playwright's optional 'exercise benchmark' tests. Then run this script
with --results-dir frontend/test-results. No uploads, database, or AI are used.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import cv2
import numpy as np
import hashlib

import imageio_ffmpeg
from benchmark_pose_sampling import PoseExtractor, analyze_set, compare, pin_one_core, sampling_fps, BENCHMARK_SUITE

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=ROOT / "frontend" / "test-results")
    parser.add_argument("--one-core", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="Inspect decoded timing without running MediaPipe")
    parser.add_argument("--fidelity", action="store_true", help="Require decoded frames to match the selected original frames exactly")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args()
    if args.one_core:
        pin_one_core()
    exercises = {item["filename"]: item["exercise_name"] for item in BENCHMARK_SUITE}
    metadata_files = [path for path in args.results_dir.glob("**/trim-metadata.json")
                      if json.loads(path.read_text(encoding="utf-8")).get("browser", "chromium") == args.browser]
    if len(metadata_files) != len(exercises):
        raise RuntimeError(f"Expected {len(exercises)} browser clip outputs; found {len(metadata_files)}")
    results = []
    with tempfile.TemporaryDirectory() as directory:
        for metadata_path in metadata_files:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            original = ROOT / "data" / "benchmark_videos" / metadata["filename"]
            client = metadata_path.parent / "client.mp4"
            server = Path(directory) / metadata["filename"]
            trim = metadata["range"]
            if args.fidelity:
                def fingerprints(video_path):
                    cap = cv2.VideoCapture(str(video_path))
                    if not cap.isOpened():
                        raise RuntimeError(f"Cannot decode {video_path}")
                    frames = []
                    while True:
                        ok, image = cap.read()
                        if not ok:
                            break
                        frames.append((cap.get(cv2.CAP_PROP_POS_MSEC) / 1000,
                                       hashlib.sha256(image.tobytes()).digest()))
                    cap.release()
                    return frames
                original_frames = fingerprints(original)
                expected = [digest for timestamp, digest in original_frames
                            if timestamp >= trim["start"] - 1e-7 and timestamp < trim["end"] - 1e-7]
                actual = [digest for _, digest in fingerprints(client)]
                # A compressed final packet can overlap the end by one frame.
                passed = len(expected) <= len(actual) <= len(expected) + 1 and actual[:len(expected)] == expected
                results.append({"filename": metadata["filename"], "passed": passed})
                print(f"{metadata['filename']}: selected={len(expected)}, decoded={len(actual)}, exact pixels={passed}", flush=True)
                continue
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", str(trim["start"]), "-t", str(trim["end"] - trim["start"]), "-i", str(original),
                            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            str(server)], check=True)
            if args.inspect:
                source_images = []
                cap = cv2.VideoCapture(str(original))
                while True:
                    ok, image = cap.read()
                    if not ok:
                        break
                    source_images.append(cv2.resize(image, (96, 54)).astype(np.float32))
                cap.release()
                source_images = np.array(source_images)
                for name, video_path in (("original", original), ("server", server), ("client", client)):
                    cap = cv2.VideoCapture(str(video_path))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    stamps = []
                    matches = []
                    decoded = 0
                    while True:
                        ok, image = cap.read()
                        if not ok:
                            break
                        if decoded < 20:
                            stamps.append(round(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000, 4))
                        if decoded in (0, 15, 45, 90):
                            errors = np.mean(np.abs(source_images - cv2.resize(image, (96, 54))), axis=(1, 2, 3))
                            best = int(np.argmin(errors))
                            matches.append((decoded, best, float(errors[best])))
                        decoded += 1
                    cap.release()
                    print(metadata["filename"], name, fps, "header", count, "decoded", decoded, "matches", matches, stamps)
                continue
            extractor = PoseExtractor(model_complexity=1, target_fps=30)
            ref_frames = extractor.extract_from_video(str(server))
            reference = analyze_set(ref_frames, fps=sampling_fps(ref_frames), exercise_name=exercises[metadata["filename"]])
            frames = extractor.extract_from_video(str(client))
            metrics = analyze_set(frames, fps=sampling_fps(frames), exercise_name=exercises[metadata["filename"]])
            comparison = compare(reference, ref_frames, metrics, frames)
            result = {**metadata, "server_reps": reference["total_reps"], "client_reps": metrics["total_reps"],
                      "server_full_reps": reference["full_reps"], "client_full_reps": metrics["full_reps"], **comparison}
            results.append(result)
            print(json.dumps(result, indent=2), flush=True)
    if args.inspect:
        return
    print(f"{'Exact source fidelity' if args.fidelity else 'Legacy server measurement regression'}: "
          f"{sum(result['passed'] for result in results)}/{len(results)} clips passed")
    if not all(result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
