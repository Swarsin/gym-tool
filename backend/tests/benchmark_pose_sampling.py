"""Real-video speed/measurement regression matrix (no network, database, or AI).

Examples:
  python backend/tests/benchmark_pose_sampling.py --original-baseline --one-core --repeats 2
  python backend/tests/benchmark_pose_sampling.py --output /tmp/pose-results.json
Thresholds are regression tolerances against Full/30, not clinical accuracy claims.
"""

import argparse
import ctypes
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

import cv2
import mediapipe as mp
ORIGINAL_OPENCV_THREADS = cv2.getNumThreads()
OPTIMIZED_OPENCV_THREADS = int(os.getenv("OPENCV_NUM_THREADS", str(ORIGINAL_OPENCV_THREADS)))

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
from app.services.video_processor import PoseExtractor
from app.services.biomechanics import analyze_set
from app.services.video_timing import frame_times, sampling_fps
from benchmark_pipeline import BENCHMARK_SUITE


def original_module(path):
    source = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT, text=True)
    module = types.ModuleType("original_" + Path(path).stem)
    module.__file__ = str(ROOT / path)
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def pin_one_core():
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    elif os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        process = kernel.GetCurrentProcess()
        mask, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(process, ctypes.byref(mask), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.SetProcessAffinityMask(process, mask.value & -mask.value):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        raise RuntimeError("CPU affinity is not supported on this platform")


def compare(reference, ref_frames, metrics, frames):
    checks = {"rep_count": metrics["total_reps"] == reference["total_reps"],
              "full_reps": metrics["full_reps"] == reference["full_reps"]}
    errors = {"boundary_s": 0.0, "tempo_s": 0.0, "velocity_relative": 0.0,
              "rom_pp": 0.0, "angle_deg": 0.0, "velocity_loss_pp": 0.0}
    if not checks["rep_count"]:
        return {"passed": False, "checks": checks, "max_errors": None}
    ref_times, times = frame_times(ref_frames), frame_times(frames)
    labels_match = True
    for before, after in zip(reference["reps_data"], metrics["reps_data"]):
        for key in ("start_idx", "peak_idx", "end_idx"):
            error = abs((ref_times[before[key]] - ref_times[0]) - (times[after[key]] - times[0]))
            errors["boundary_s"] = max(errors["boundary_s"], error)
        for key in ("concentric_tempo_s", "eccentric_tempo_s"):
            errors["tempo_s"] = max(errors["tempo_s"], abs(before[key] - after[key]))
        errors["velocity_relative"] = max(errors["velocity_relative"],
            abs(before["mean_velocity_mps"] - after["mean_velocity_mps"]) / max(.01, abs(before["mean_velocity_mps"])))
        for key in ("concentric_rom_pct", "eccentric_rom_pct"):
            errors["rom_pp"] = max(errors["rom_pp"], abs(before[key] - after[key]))
        for key in ("left_elbow_flare_deg", "right_elbow_flare_deg", "shoulder_tilt_deg"):
            errors["angle_deg"] = max(errors["angle_deg"], abs(before[key] - after[key]))
        for key in ("is_partial_rep", "asymmetry_status", "elevated_shoulder_side"):
            labels_match &= before[key] == after[key]
    before_vbt, after_vbt = reference["vbt_summary"], metrics["vbt_summary"]
    errors["velocity_loss_pp"] = abs(before_vbt["velocity_loss_pct"] - after_vbt["velocity_loss_pct"])
    checks.update({key: errors[key] <= threshold + 1e-7 for key, threshold in {
        "boundary_s": .1, "tempo_s": .1, "velocity_relative": .05,
        "rom_pp": 5, "angle_deg": 5, "velocity_loss_pp": 5}.items()})
    checks["classifications"] = bool(labels_match and
        before_vbt["velocity_loss_available"] == after_vbt["velocity_loss_available"] and
        before_vbt["estimated_rpe"] == after_vbt["estimated_rpe"] and
        before_vbt["estimated_rir"] == after_vbt["estimated_rir"] and
        reference["asymmetry_analysis"]["asymmetry_classification"] == metrics["asymmetry_analysis"]["asymmetry_classification"] and
        reference["asymmetry_analysis"]["fatigue_drift_detected"] == metrics["asymmetry_analysis"]["fatigue_drift_detected"])
    return {"passed": all(checks.values()), "checks": checks, "max_errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--one-core", action="store_true")
    parser.add_argument("--original-baseline", action="store_true", help="Compare against extractor/analysis from git HEAD")
    parser.add_argument("--configs", nargs="+", choices=["full_30", "full_25", "full_20", "lite_30", "full_15", "lite_20"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-pass", action="store_true", help="Exit nonzero unless a faster candidate passes every clip")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.one_core:
        pin_one_core()
    original_extractor = original_module("backend/app/services/video_processor.py").PoseExtractor if args.original_baseline else PoseExtractor
    original_analyze = original_module("backend/app/services/biomechanics.py").analyze_set if args.original_baseline else analyze_set
    configs = [("full_30", 1, 30), ("full_25", 1, 25), ("full_20", 1, 20), ("lite_30", 0, 30), ("full_15", 1, 15), ("lite_20", 0, 20)]
    if args.configs:
        configs = [config for config in configs if config[0] in args.configs]
    all_results = []
    print(f"CPU affinity: {'one logical core' if args.one_core else 'unrestricted'}; repeats: {args.repeats}", flush=True)
    for item in BENCHMARK_SUITE:
        video = ROOT / "data" / "benchmark_videos" / item["filename"]
        if not video.exists():
            raise FileNotFoundError(video)
        baseline_runs = []
        for _ in range(args.repeats):
            cv2.setNumThreads(ORIGINAL_OPENCV_THREADS if args.original_baseline else OPTIMIZED_OPENCV_THREADS)
            extractor = original_extractor(model_complexity=1)
            t0 = time.perf_counter()
            frames = extractor.extract_from_video(str(video))
            elapsed = time.perf_counter() - t0
            metrics = original_analyze(frames, fps=30, exercise_name=item["exercise_name"])
            baseline_runs.append((elapsed, frames, metrics))
        baseline_seconds, ref_frames, reference = sorted(baseline_runs, key=lambda r: r[0])[len(baseline_runs) // 2]
        baseline_seconds = statistics.median(r[0] for r in baseline_runs)
        print(f"\n{video.name}: baseline {baseline_seconds:.2f}s; reps {reference['total_reps']}/{reference['full_reps']} total/full", flush=True)
        runs = {name: [] for name, _, _ in configs}
        for repeat in range(args.repeats):
            for name, model, fps in (configs if repeat % 2 == 0 else configs[::-1]):
                cv2.setNumThreads(OPTIMIZED_OPENCV_THREADS)
                extractor = PoseExtractor(model_complexity=model, target_fps=fps)
                t0 = time.perf_counter()
                frames = extractor.extract_from_video(str(video))
                elapsed = time.perf_counter() - t0
                metrics = analyze_set(frames, fps=sampling_fps(frames), exercise_name=item["exercise_name"])
                comparison = compare(reference, ref_frames, metrics, frames)
                runs[name].append({"seconds": elapsed, "profile": extractor.last_profile,
                    "total_reps": metrics["total_reps"], "full_reps": metrics["full_reps"],
                    "ground_truth_total": metrics["total_reps"] == item["expected_total_reps"],
                    "ground_truth_full": metrics["full_reps"] == item["expected_full_reps"],
                    "comparison": comparison})
                print(f"  {name:8} run {repeat + 1}: {elapsed:6.2f}s; reps {metrics['total_reps']}/{metrics['full_reps']}; regression {'PASS' if comparison['passed'] else 'FAIL'}", flush=True)
        for name, model, fps in configs:
            data = runs[name]
            seconds = statistics.median(r["seconds"] for r in data)
            all_results.append({"file": video.name, "config": name, "model": model, "target_fps": fps,
                "baseline_seconds": baseline_seconds, "seconds": seconds, "speedup": baseline_seconds / seconds,
                "regression_passed": all(r["comparison"]["passed"] for r in data),
                "ground_truth_passed": all(r["ground_truth_total"] and r["ground_truth_full"] for r in data), "runs": data})
    summary = []
    print("\nAggregate (all clips and repeats must pass):", flush=True)
    for name, _, _ in configs:
        rows = [r for r in all_results if r["config"] == name]
        baseline = sum(r["baseline_seconds"] for r in rows)
        seconds = sum(r["seconds"] for r in rows)
        regression = all(r["regression_passed"] for r in rows)
        truth = all(r["ground_truth_passed"] for r in rows)
        result = {"config": name, "baseline_seconds": baseline, "seconds": seconds, "speedup": baseline / seconds,
                  "regression_passed": regression, "ground_truth_passed": truth}
        summary.append(result)
        print(f"  {name:8}: {seconds:.2f}s vs {baseline:.2f}s ({baseline / seconds:.2f}x); regression={regression}; human counts={truth}", flush=True)
    report = {"original_baseline": args.original_baseline, "one_core": args.one_core, "repeats": args.repeats,
              "runtime": {"python": sys.version, "platform": platform.platform(),
                          "opencv": cv2.__version__, "mediapipe": mp.__version__},
              "original_opencv_threads": ORIGINAL_OPENCV_THREADS,
              "optimized_opencv_threads": OPTIMIZED_OPENCV_THREADS,
              "summary": summary, "results": all_results}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.require_pass and not any(r["regression_passed"] and r["ground_truth_passed"] and r["speedup"] > 1 for r in summary):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
