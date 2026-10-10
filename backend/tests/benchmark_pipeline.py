import os
import sys
import time
import json
import numpy as np

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.video_processor import PoseExtractor
from app.services.biomechanics import analyze_set, extract_exercise_trajectory

# HUMAN GROUND TRUTH BENCHMARK SUITE:
# Hand-verified ground-truth rep counts and ROM distributions verified against human video review.
BENCHMARK_SUITE = [
    {
        "filename": "lat_pulldown_online_log64.mp4",
        "exercise_name": "Pull-Up / Chin-Up",
        "modality": "Bodyweight Vertical Ascension",
        "expected_total_reps": 3,
        "expected_full_reps": 3,
        "notes": "Pull-up exercise with 3 full ROM reps."
    },
    {
        "filename": "pullup_online_log63.mp4",
        "exercise_name": "Pull-Up / Chin-Up",
        "modality": "Bodyweight Vertical Ascension",
        "expected_total_reps": 5,
        "expected_full_reps": 5,
        "notes": "5 pull-ups; last rep is slightly shorter at the top."
    },
    {
        "filename": "pullup_online_log61.mp4",
        "exercise_name": "Pull-Up / Chin-Up",
        "modality": "Bodyweight Vertical Ascension",
        "expected_total_reps": 8,
        "expected_full_reps": 2,
        "notes": "8 pull-ups: only 1st and 8th are full lockout; 6 partials in between."
    },
    {
        "filename": "lat_pulldown_online_log57.mp4",
        "exercise_name": "Lat Pulldown (Lower-Lat Bias)",
        "modality": "Vertical Cable Pull Down",
        "expected_total_reps": 5,
        "expected_full_reps": 3,
        "notes": "5 lat pulldowns: Rep 1 deep to chest, Reps 2 & 3 good ROM, Reps 4 & 5 partials."
    }
]

def run_multi_video_benchmark():
    print("=" * 70)
    print("MULTI-VIDEO ONLINE BENCHMARK TEST SUITE (REAL ONLINE VIDEOS)")
    print("=" * 70)

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    video_dir = os.path.join(base_dir, "data", "benchmark_videos")

    complexity_arg = int(sys.argv[1]) if len(sys.argv) > 1 else None
    extractor = PoseExtractor(model_complexity=complexity_arg)
    print(f"Using MediaPipe Model: {os.path.basename(extractor.model_path)}")
    overall_results = []

    for item in BENCHMARK_SUITE:
        fname = item["filename"]
        ex_name = item["exercise_name"]
        modality = item["modality"]
        vpath = os.path.join(video_dir, fname)

        if not os.path.exists(vpath):
            print(f"[SKIP] Video not found: {fname}")
            continue

        fsize_mb = os.path.getsize(vpath) / (1024 * 1024)
        print(f"\nEvaluating: {fname} ({fsize_mb:.2f} MB)")
        print(f"Target Exercise: {ex_name} [{modality}]")

        # 1. Pose Extraction
        t0 = time.time()
        frame_data = extractor.extract_from_video(vpath)
        t_extract = time.time() - t0
        fps = len(frame_data) / max(0.01, t_extract)

        # 2. Kinematic Analysis
        t1 = time.time()
        metrics = analyze_set(frame_data, fps=30.0, exercise_name=ex_name)
        t_kinematics_ms = (time.time() - t1) * 1000.0

        raw_traj, smooth_traj, torso_norm = extract_exercise_trajectory(frame_data, exercise_name=ex_name)
        total_reps = metrics.get("total_reps", 0)
        full_reps = metrics.get("full_reps", 0)
        partial_reps = metrics.get("partial_reps", 0)
        avg_tempo = metrics.get("avg_eccentric_tempo", 0.0)
        avg_flare = metrics.get("avg_elbow_flare", 0.0)
        vbt = metrics.get("vbt_summary", {})
        mean_v = vbt.get("avg_concentric_velocity_mps", 0.0)
        vel_loss = vbt.get("velocity_loss_pct")
        reps = metrics.get("reps_data", [])

        print(f"   [OK] Processed {len(frame_data)} frames in {t_extract:.2f}s ({fps:.1f} FPS)")
        print(f"   [OK] Kinematics Engine Latency: {t_kinematics_ms:.2f}ms")
        print(f"   * Detected Total Reps: {total_reps} (Full ROM: {full_reps}, Partials: {partial_reps})")
        print(f"   * Mean Concentric Velocity: {mean_v:.2f} m/s")
        print(f"   * Avg Eccentric Tempo: {avg_tempo:.1f}s | Avg 3D Flare: {avg_flare:.1f} deg")
        if vel_loss is not None:
            print(f"   * Set Velocity Loss: {vel_loss:.1f}%")

        if reps:
            for r in reps[:3]:
                print(f"      - Rep #{r['rep_number']}: Speed={r['mean_velocity_mps']} m/s, Conc={r['concentric_rom_pct']}%, Ecc={r['eccentric_rom_pct']}%, Tempo={r['eccentric_tempo_s']}s/{r['concentric_tempo_s']}s")

        expected_total = item.get("expected_total_reps")
        expected_full = item.get("expected_full_reps")
        rep_match = (total_reps == expected_total) if expected_total is not None else True

        overall_results.append({
            "file": fname,
            "exercise": ex_name,
            "frames": len(frame_data),
            "reps": total_reps,
            "expected_reps": expected_total,
            "rep_match": rep_match,
            "full_reps": full_reps,
            "expected_full": expected_full,
            "mean_v": mean_v,
            "latency_ms": t_kinematics_ms
        })

    print("\n" + "=" * 80)
    print("BENCHMARK AGGREGATE SUMMARY & ACCURACY SCORECARD")
    print("=" * 80)
    print(f"{'Video File':<30} | {'Exercise':<18} | {'Act/Exp':<9} | {'Match':<6} | {'Speed':<8} | {'Latency'}")
    print("-" * 80)
    correct_matches = 0
    total_evaluated = len(overall_results)

    for r in overall_results:
        match_str = "PASS" if r["rep_match"] else "FAIL"
        if r["rep_match"]:
            correct_matches += 1
        rep_ratio = f"{r['reps']}/{r['expected_reps']}"
        print(f"{r['file']:<30} | {r['exercise']:<18} | {rep_ratio:<9} | {match_str:<6} | {r['mean_v']:<6.2f}m/s | {r['latency_ms']:.1f}ms")
    print("=" * 80)

    if total_evaluated > 0:
        accuracy_pct = (correct_matches / total_evaluated) * 100.0
        print(f"Rep-Count Human Ground-Truth Accuracy: {accuracy_pct:.1f}% ({correct_matches}/{total_evaluated} videos exact match)")
        assert correct_matches == total_evaluated, f"Rep count mismatch vs human ground truth: {correct_matches}/{total_evaluated} passed."
        print("[ALL PASSED] Rep counts match verified human ground truth on all benchmark clips.")
    else:
        print("[WARNING] No benchmark videos were evaluated (missing files).")
    print("=" * 80)

if __name__ == "__main__":
    run_multi_video_benchmark()
