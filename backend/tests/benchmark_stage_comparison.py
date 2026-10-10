"""
Comprehensive Benchmark Script: Stage-by-Stage Performance Comparison
Measures isolated performance and latency delta across:
  Stage 3: MediaPipe Pose Model (Heavy vs Full vs Lite)
  Stage 4: Video Encoding (Double-Pass vs Single-Pass Pipe)
  Stage 1 & 2: Architectural Concurrency & Two-Phase Delivery
"""

import os
import sys
import time
import tempfile
import subprocess
import numpy as np

# Ensure backend directory is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.video_processor import PoseExtractor
from app.services.biomechanics import analyze_set, extract_exercise_trajectory
import imageio_ffmpeg
import cv2

BENCHMARK_VIDEOS = [
    {
        "filename": "lat_pulldown_online_log64.mp4",
        "exercise": "Pull-Up / Chin-Up",
    },
    {
        "filename": "pullup_online_log63.mp4",
        "exercise": "Pull-Up / Chin-Up",
    },
    {
        "filename": "pullup_online_log61.mp4",
        "exercise": "Pull-Up / Chin-Up",
    },
    {
        "filename": "lat_pulldown_online_log57.mp4",
        "exercise": "Lat Pulldown (Lower-Lat Bias)",
    },
]


def test_mediapipe_models(video_dir):
    print("\n" + "=" * 75)
    print("STAGE 3 BENCHMARK: MediaPipe Pose Model Comparison (Heavy vs Full vs Lite)")
    print("=" * 75)

    extractor_heavy = PoseExtractor(model_complexity=2)
    extractor_full = PoseExtractor(model_complexity=1)
    extractor_lite = PoseExtractor(model_complexity=0)

    results = []

    for item in BENCHMARK_VIDEOS:
        fname = item["filename"]
        vpath = os.path.join(video_dir, fname)
        if not os.path.exists(vpath):
            continue

        print(f"\nEvaluating: {fname}...")

        # 1. Heavy Model
        t0 = time.time()
        frames_heavy = extractor_heavy.extract_from_video(vpath)
        t_heavy = time.time() - t0
        fps_heavy = len(frames_heavy) / max(0.01, t_heavy)
        m_heavy = analyze_set(frames_heavy, fps=30.0, exercise_name=item["exercise"])
        reps_heavy = m_heavy.get("total_reps", 0)

        # 2. Full Model
        t0 = time.time()
        frames_full = extractor_full.extract_from_video(vpath)
        t_full = time.time() - t0
        fps_full = len(frames_full) / max(0.01, t_full)
        m_full = analyze_set(frames_full, fps=30.0, exercise_name=item["exercise"])
        reps_full = m_full.get("total_reps", 0)

        # 3. Lite Model
        t0 = time.time()
        frames_lite = extractor_lite.extract_from_video(vpath)
        t_lite = time.time() - t0
        fps_lite = len(frames_lite) / max(0.01, t_lite)
        m_lite = analyze_set(frames_lite, fps=30.0, exercise_name=item["exercise"])
        reps_lite = m_lite.get("total_reps", 0)

        time_saved = t_heavy - t_full
        pct_reduced = (time_saved / t_heavy) * 100.0
        speedup = t_heavy / max(0.01, t_full)

        results.append({
            "file": fname,
            "frames": len(frames_heavy),
            "t_heavy": t_heavy,
            "fps_heavy": fps_heavy,
            "reps_heavy": reps_heavy,
            "t_full": t_full,
            "fps_full": fps_full,
            "reps_full": reps_full,
            "t_lite": t_lite,
            "fps_lite": fps_lite,
            "reps_lite": reps_lite,
            "time_saved": time_saved,
            "pct_reduced": pct_reduced,
            "speedup": speedup,
            # Cache full frames and metrics for video renderer test
            "frames_full_data": frames_full,
            "metrics_full": m_full,
            "exercise": item["exercise"]
        })

        print(f"  * Heavy : {t_heavy:.2f}s ({fps_heavy:.1f} FPS) -> Reps: {reps_heavy}")
        print(f"  * Full  : {t_full:.2f}s ({fps_full:.1f} FPS) -> Reps: {reps_full} [{speedup:.2f}x faster, -{pct_reduced:.1f}% time]")
        print(f"  * Lite  : {t_lite:.2f}s ({fps_lite:.1f} FPS) -> Reps: {reps_lite} [{t_heavy / max(0.01, t_lite):.2f}x faster]")

    print("\n" + "-" * 75)
    print("STAGE 3 AGGREGATE SUMMARY: Heavy vs Full")
    print("-" * 75)
    print(f"{'Video File':<30} | {'Heavy':<8} | {'Full':<8} | {'Saved (s)':<9} | {'Reduction':<9} | {'Speedup'}")
    print("-" * 75)
    total_heavy = sum(r["t_heavy"] for r in results)
    total_full = sum(r["t_full"] for r in results)
    total_lite = sum(r["t_lite"] for r in results)
    for r in results:
        print(f"{r['file']:<30} | {r['t_heavy']:>6.2f}s | {r['t_full']:>6.2f}s | {r['time_saved']:>7.2f}s | -{r['pct_reduced']:>6.1f}% | {r['speedup']:>6.2f}x")
    print("-" * 75)
    tot_saved = total_heavy - total_full
    tot_pct = (tot_saved / total_heavy) * 100.0
    tot_speedup = total_heavy / max(0.01, total_full)
    print(f"{'TOTAL / AVERAGE':<30} | {total_heavy:>6.2f}s | {total_full:>6.2f}s | {tot_saved:>7.2f}s | -{tot_pct:>6.1f}% | {tot_speedup:>6.2f}x")

    return results


def test_video_render_encoding(video_dir, pipeline_results):
    print("\n" + "=" * 75)
    print("STAGE 4 BENCHMARK: Video Encoding (Double-Pass vs Single-Pass Pipe)")
    print("=" * 75)

    from app.services.video_renderer import render_overlay_video

    encoding_results = []
    temp_dir = tempfile.gettempdir()

    for r in pipeline_results:
        fname = r["file"]
        vpath = os.path.join(video_dir, fname)
        frames_full = r["frames_full_data"]
        metrics = r["metrics_full"]

        out_double = os.path.join(temp_dir, f"bench_double_{fname}")
        out_single = os.path.join(temp_dir, f"bench_single_{fname}")

        print(f"\nEvaluating render for: {fname} ({r['frames']} frames)...")

        # 1. Double-Pass (Old)
        t0 = time.time()
        render_overlay_video(vpath, frames_full, metrics, out_double, force_double_pass=True)
        t_double = time.time() - t0
        sz_double = os.path.getsize(out_double) / 1024.0 if os.path.exists(out_double) else 0.0

        # 2. Single-Pass (New)
        t0 = time.time()
        render_overlay_video(vpath, frames_full, metrics, out_single, force_double_pass=False)
        t_single = time.time() - t0
        sz_single = os.path.getsize(out_single) / 1024.0 if os.path.exists(out_single) else 0.0

        time_saved = t_double - t_single
        pct_reduced = (time_saved / t_double) * 100.0
        speedup = t_double / max(0.01, t_single)

        encoding_results.append({
            "file": fname,
            "frames": r["frames"],
            "t_double": t_double,
            "t_single": t_single,
            "time_saved": time_saved,
            "pct_reduced": pct_reduced,
            "speedup": speedup,
            "sz_single": sz_single
        })

        print(f"  * Double-Pass (Old) : {t_double:.2f}s (File: {sz_double:.1f} KB)")
        print(f"  * Single-Pass (New) : {t_single:.2f}s (File: {sz_single:.1f} KB) [{speedup:.2f}x faster, -{pct_reduced:.1f}% time]")

        for p in [out_double, out_single]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    print("\n" + "-" * 75)
    print("STAGE 4 AGGREGATE SUMMARY: Double-Pass vs Single-Pass")
    print("-" * 75)
    print(f"{'Video File':<30} | {'Double-Pass':<11} | {'Single-Pass':<11} | {'Saved (s)':<9} | {'Reduction':<9} | {'Speedup'}")
    print("-" * 75)
    total_double = sum(e["t_double"] for e in encoding_results)
    total_single = sum(e["t_single"] for e in encoding_results)
    for e in encoding_results:
        print(f"{e['file']:<30} | {e['t_double']:>9.2f}s | {e['t_single']:>9.2f}s | {e['time_saved']:>7.2f}s | -{e['pct_reduced']:>6.1f}% | {e['speedup']:>6.2f}x")
    print("-" * 75)
    tot_saved = total_double - total_single
    tot_pct = (tot_saved / total_double) * 100.0
    tot_speedup = total_double / max(0.01, total_single)
    print(f"{'TOTAL / AVERAGE':<30} | {total_double:>9.2f}s | {total_single:>9.2f}s | {tot_saved:>7.2f}s | -{tot_pct:>6.1f}% | {tot_speedup:>6.2f}x")

    return encoding_results


def test_end_to_end_concurrency(pipeline_results, encoding_results):
    print("\n" + "=" * 75)
    print("STAGE 1 & 2 BENCHMARK: End-to-End Latency to User Screen Unlock")
    print("=" * 75)
    print("Comparing time until user sees workout results (Scorecard & 3D Viewer):")
    print("  Architecture A (Original)  : Sequential (Heavy Pose + Kinematics + Gemini AI + Double-Pass Render)")
    print("  Architecture B (Optimized) : Two-Phase Delivery (Full Pose + Kinematics + Gemini AI Concurrent)")
    print("-" * 75)

    GEMINI_LATENCY = 3.5  # Typical real-world Gemini 1.5 Flash API latency (seconds)
    KINEMATICS_LATENCY = 0.05  # Average kinematics compute time (50ms)

    e2e_results = []
    print(f"{'Video File':<30} | {'Old Latency':<12} | {'New Unlock':<12} | {'Time Saved':<10} | {'% Faster'}")
    print("-" * 75)

    for p, e in zip(pipeline_results, encoding_results):
        fname = p["file"]
        # Old Sequential: Heavy Pose + Kinematics + Gemini + Double-Pass Render
        old_total = p["t_heavy"] + KINEMATICS_LATENCY + GEMINI_LATENCY + e["t_double"]

        # Stage 1 Concurrent: Heavy Pose + Kinematics + max(Gemini, Double-Pass Render)
        concurrent_total = p["t_heavy"] + KINEMATICS_LATENCY + max(GEMINI_LATENCY, e["t_double"])

        # Metrics unlock before either coaching or video rendering finishes.
        new_unlock_time = p["t_full"] + KINEMATICS_LATENCY

        # Full completion with single-pass render in background
        new_video_ready_time = p["t_full"] + KINEMATICS_LATENCY + max(GEMINI_LATENCY, e["t_single"])

        time_saved = old_total - new_unlock_time
        pct_faster = (time_saved / old_total) * 100.0
        speedup = old_total / max(0.01, new_unlock_time)

        e2e_results.append({
            "file": fname,
            "old_total": old_total,
            "concurrent_total": concurrent_total,
            "new_unlock_time": new_unlock_time,
            "new_video_ready_time": new_video_ready_time,
            "time_saved": time_saved,
            "pct_faster": pct_faster,
            "speedup": speedup
        })

        print(f"{fname:<30} | {old_total:>10.2f}s | {new_unlock_time:>10.2f}s | {time_saved:>8.2f}s | -{pct_faster:>5.1f}% ({speedup:.2f}x)")

    print("-" * 75)
    tot_old = sum(r["old_total"] for r in e2e_results)
    tot_new = sum(r["new_unlock_time"] for r in e2e_results)
    tot_saved = tot_old - tot_new
    tot_pct = (tot_saved / tot_old) * 100.0
    tot_speedup = tot_old / max(0.01, tot_new)
    print(f"{'TOTAL / AVERAGE':<30} | {tot_old:>10.2f}s | {tot_new:>10.2f}s | {tot_saved:>8.2f}s | -{tot_pct:>5.1f}% ({tot_speedup:.2f}x)")
    print("=" * 75)


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    video_dir = os.path.join(base_dir, "data", "benchmark_videos")

    if not os.path.exists(video_dir):
        print(f"Error: Video directory not found at {video_dir}")
        return

    # Run tests stage by stage
    pipeline_results = test_mediapipe_models(video_dir)
    encoding_results = test_video_render_encoding(video_dir, pipeline_results)
    test_end_to_end_concurrency(pipeline_results, encoding_results)


if __name__ == "__main__":
    main()
