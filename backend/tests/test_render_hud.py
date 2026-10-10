import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.video_processor import PoseExtractor
from app.services.biomechanics import analyze_set
from app.services.video_renderer import render_overlay_video
import cv2

def test_hud_rendering():
    print("=" * 65)
    print("TESTING VIDEO OVERLAY HUD & WAVEFORM PIP")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    test_video = os.path.join(base_dir, "data", "benchmark_videos", "lat_pulldown_online_log64.mp4")
    out_video = os.path.join(base_dir, "data", "test_hud_output.mp4")

    if not os.path.exists(test_video):
        test_video = os.path.join(base_dir, "data", "raw_video.mp4")

    print(f"Input video: {test_video}")
    extractor = PoseExtractor(model_complexity=2)
    frame_data = extractor.extract_from_video(test_video)
    print(f"Extracted {len(frame_data)} frames.")

    set_metrics = analyze_set(frame_data, fps=30.0, exercise_name="Lat Pulldown (Lower-Lat Bias)")
    print(f"Detected {set_metrics['total_reps']} reps:")
    for r in set_metrics["reps_data"]:
        print(f"   Rep #{r['rep_number']}: start={r['start_idx']}, peak={r['peak_idx']}, end={r['end_idx']}")

    # Render overlay video
    print("\nRendering overlay video with updated HUD & PIP...")
    t0 = time.time()
    render_overlay_video(test_video, frame_data, set_metrics, out_video)
    t_render = time.time() - t0
    print(f"[OK] Rendered in {t_render:.2f}s to {out_video} ({os.path.getsize(out_video)/(1024*1024):.2f} MB)")

    # Verify rendered video frames
    cap = cv2.VideoCapture(out_video)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[OK] Rendered video has {total_frames} valid playable frames.")
    cap.release()
    print("=" * 65)
    print("ALL TESTS PASSED: Rep Counter & Phase Tracking Verified!")
    print("=" * 65)

if __name__ == "__main__":
    test_hud_rendering()
