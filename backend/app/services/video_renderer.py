"""
Video Renderer — Generates an annotated overlay video with confidence-coded skeletal landmarks,
static scene reference lines, and a synchronized Picture-in-Picture (PIP) Kinematic Waveform Dashboard.
"""

import os
import cv2
import tempfile
import numpy as np
from typing import List, Dict, Any, Tuple, Optional


COLOR_CONF_HIGH = (80, 230, 80)     # High confidence (Green)
COLOR_CONF_MED  = (0, 190, 255)     # Medium confidence (Amber)
COLOR_CONF_LOW  = (140, 140, 140)   # Low / Interpolated (Dimmed Gray)
COLOR_BAR       = (255, 220, 80)     # Pull-up bar line (Cyan/Blue)
COLOR_HUD_BG    = (20, 20, 20)       # Dark HUD background
COLOR_TEXT      = (245, 245, 245)    # White text

BONE_CONNECTIONS = [
    ('shoulder_r', 'elbow_r'),
    ('elbow_r', 'wrist_r'),
    ('shoulder_l', 'elbow_l'),
    ('elbow_l', 'wrist_l'),
    ('shoulder_r', 'hip_r'),
    ('shoulder_l', 'hip_l'),
    ('shoulder_l', 'shoulder_r'),
    ('hip_l', 'hip_r'),
]


def _to_pixel(landmark: List[float], width: int, height: int) -> Tuple[int, int]:
    return (int(landmark[0] * width), int(landmark[1] * height))


def _draw_confidence_skeleton(
    frame: np.ndarray,
    landmarks: Dict[str, List[float]],
    width: int,
    height: int
):
    """Draws skeleton bones colored by measurement confidence."""
    if not landmarks:
        return

    for name_a, name_b in BONE_CONNECTIONS:
        if name_a not in landmarks or name_b not in landmarks:
            continue
        pt_a = _to_pixel(landmarks[name_a], width, height)
        pt_b = _to_pixel(landmarks[name_b], width, height)

        conf_a = landmarks[name_a][3] if len(landmarks[name_a]) > 3 else 1.0
        conf_b = landmarks[name_b][3] if len(landmarks[name_b]) > 3 else 1.0
        min_conf = min(conf_a, conf_b)

        if min_conf >= 0.70:
            color = COLOR_CONF_HIGH
            thickness = 3
        elif min_conf >= 0.40:
            color = COLOR_CONF_MED
            thickness = 2
        else:
            color = COLOR_CONF_LOW
            thickness = 1

        cv2.line(frame, pt_a, pt_b, color, thickness, cv2.LINE_AA)

    # Draw joint circles
    for name, coords in landmarks.items():
        pt = _to_pixel(coords, width, height)
        conf = coords[3] if len(coords) > 3 else 1.0
        c_color = COLOR_CONF_HIGH if conf >= 0.70 else (COLOR_CONF_MED if conf >= 0.40 else COLOR_CONF_LOW)
        cv2.circle(frame, pt, 5, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 5, c_color, 2, cv2.LINE_AA)


def _render_pip_dashboard(
    frame: np.ndarray,
    frame_idx: int,
    n_frames: int,
    traj: np.ndarray,
    reps_data: List[Dict[str, Any]],
    width: int,
    height: int
):
    """
    Renders a synchronized Picture-in-Picture (PIP) kinematic waveform mini-panel
    in the bottom-right corner with a moving playhead line and labeled rep zones.
    """
    # Very small or pathological aspect ratios cannot fit a readable chart.
    if width < 120 or height < 100 or n_frames < 2 or len(traj) < 2:
        return

    pip_w = int(width * 0.38)
    pip_h = int(height * 0.22)
    margin = 20

    x1 = width - pip_w - margin
    y1 = height - pip_h - margin
    x2 = x1 + pip_w
    y2 = y1 + pip_h

    # Semi-transparent dark background (in-place slice to avoid full frame copying)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 > x1 and y2 > y1:
        sub_img = frame[y1:y2, x1:x2]
        rect = np.full_like(sub_img, COLOR_HUD_BG)
        cv2.addWeighted(rect, 0.85, sub_img, 0.15, 0, sub_img)
        frame[y1:y2, x1:x2] = sub_img
    cv2.rectangle(frame, (x1, y1), (x2, y2), (60, 60, 60), 1)

    # Header title
    cv2.putText(
        frame, "KINEMATIC WAVEFORM (SYNCED)",
        (x1 + 10, y1 + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1, cv2.LINE_AA
    )

    plot_x1 = x1 + 10
    plot_x2 = x2 - 10
    plot_y1 = y1 + 26
    plot_y2 = y2 - 10
    plot_w = plot_x2 - plot_x1
    plot_h = plot_y2 - plot_y1
    if plot_w <= 1 or plot_h <= 1:
        return

    timeline_len = max(2, n_frames)
    timeline_denom = timeline_len - 1
    traj_denom = max(1, len(traj) - 1)

    # Draw rep boundary shaded regions and rep number badges
    for rep in reps_data:
        s_idx = rep.get("start_idx", 0)
        e_idx = rep.get("end_idx", timeline_len - 1)
        r_num = rep.get("rep_number", 1)
        is_active = (s_idx <= frame_idx <= e_idx)

        s_idx = max(0, min(timeline_len - 1, int(s_idx)))
        e_idx = max(s_idx, min(timeline_len - 1, int(e_idx)))
        rx1 = plot_x1 + int((s_idx / timeline_denom) * plot_w)
        rx2 = plot_x1 + int((e_idx / timeline_denom) * plot_w)
        
        is_partial = rep.get("is_partial_rep", False)
        box_color = (60, 30, 30) if is_partial else ((30, 60, 30) if is_active else (20, 35, 20))
        cv2.rectangle(frame, (rx1, plot_y1), (rx2, plot_y2), box_color, -1)
        cv2.line(frame, (rx1, plot_y1), (rx1, plot_y2), (0, 240, 255) if is_active else (80, 80, 80), 1)
        cv2.line(frame, (rx2, plot_y1), (rx2, plot_y2), (0, 240, 255) if is_active else (80, 80, 80), 1)

        # Rep number label in mini chart
        mid_rx = (rx1 + rx2) // 2
        cv2.putText(
            frame, f"#{r_num}",
            (max(plot_x1, min(plot_x2 - 16, mid_rx - 6)), plot_y1 + 12),
            cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 240, 255) if is_active else (150, 150, 150), 1, cv2.LINE_AA
        )

    # Normalize trajectory for plotting
    min_t, max_t = float(np.min(traj)), float(np.max(traj))
    span_t = max(1e-4, max_t - min_t)

    pts = []
    for i in range(len(traj)):
        px = plot_x1 + int((i / traj_denom) * plot_w)
        norm_val = (traj[i] - min_t) / span_t
        py = plot_y2 - int(norm_val * plot_h)
        pts.append((px, py))

    for k in range(len(pts) - 1):
        cv2.line(frame, pts[k], pts[k + 1], (255, 200, 50), 2, cv2.LINE_AA)

    # Draw moving playhead line & tracking dot
    curr_f = max(0, min(frame_idx, timeline_len - 1))
    progress = curr_f / timeline_denom
    playhead_x = plot_x1 + int(progress * plot_w)
    cv2.line(frame, (playhead_x, plot_y1), (playhead_x, plot_y2), (0, 240, 255), 2, cv2.LINE_AA)

    traj_idx = min(len(pts) - 1, max(0, int(round(progress * traj_denom))))
    if pts:
        cv2.circle(frame, pts[traj_idx], 4, (0, 255, 255), -1)
        cv2.circle(frame, pts[traj_idx], 6, (0, 200, 255), 1)


def render_overlay_video(
    video_path: str,
    frame_data: List[Dict[str, Any]],
    set_metrics: Dict[str, Any],
    output_path: str,
    active_range: Optional[Tuple[int, int]] = None,
    force_double_pass: bool = False
) -> str:
    """
    Renders video with confidence-coded skeleton, static bar line, and synchronized PIP dashboard.
    If active_range=(start_frame, end_frame) is provided, automatically crops the output video
    to only the active workout set (skipping camera setup and cooldown walk-back).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open input video: {video_path}")

    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if not np.isfinite(orig_fps) or orig_fps <= 0:
        orig_fps = 30.0
    orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = len(frame_data)
    if total_frames == 0:
        cap.release()
        raise ValueError("Cannot render overlay without extracted frame data")

    # Active range boundaries (if trimming active set)
    start_frame = max(0, active_range[0]) if active_range else 0
    end_frame = min(total_frames - 1, active_range[1]) if active_range else total_frames - 1
    if end_frame < start_frame:
        start_frame, end_frame = 0, total_frames - 1

    sliced_frames = frame_data[start_frame:end_frame + 1]
    active_len = len(sliced_frames)

    # Scale resolution to max 720p to preserve server memory and speed up encoding
    max_dim = max(orig_w, orig_h) if (orig_w > 0 and orig_h > 0) else 720
    target_max = 720
    scale = target_max / max_dim if max_dim > target_max else 1.0
    out_w = int(orig_w * scale) if orig_w > 0 else 720
    out_h = int(orig_h * scale) if orig_h > 0 else 720
    out_w = out_w if out_w % 2 == 0 else out_w - 1
    out_h = out_h if out_h % 2 == 0 else out_h - 1
    if out_w < 2 or out_h < 2:
        cap.release()
        raise ValueError(f"Invalid input video dimensions: {orig_w}x{orig_h}")

    from app.services.video_timing import render_schedule, frame_times
    times = frame_times(frame_data)
    render_fps, schedule = render_schedule(frame_data, start_frame, end_frame, orig_fps)

    # Single-pass FFmpeg stdin pipe: streams raw frames directly to H.264 encoder
    # Eliminates intermediate disk writes, temp files, and double-pass encoding
    ffmpeg_proc = None
    writer = None
    temp_render = None

    if not force_double_pass:
        try:
            import subprocess
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            ffmpeg_cmd = [
                ffmpeg_bin,
                '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-s', f'{out_w}x{out_h}',
                '-pix_fmt', 'bgr24',
                '-r', str(render_fps),
                '-i', '-',
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_path
            ]
            ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except Exception as pipe_err:
            print(f"Notice: Direct FFmpeg pipe fallback to VideoWriter: {pipe_err}")
            ffmpeg_proc = None

    if ffmpeg_proc is None:
        temp_dir = tempfile.gettempdir()
        temp_render = os.path.join(temp_dir, f"temp_render_{os.path.basename(output_path)}")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(temp_render, fourcc, render_fps, (out_w, out_h))
        if not writer.isOpened():
            cap.release()
            raise ValueError(f"Cannot create fallback video writer at: {temp_render}")

    from app.services.biomechanics import extract_exercise_trajectory

    reps_data = set_metrics.get("reps_data", [])
    total_reps = set_metrics.get("total_reps", 0)
    exercise_name = set_metrics.get("exercise_name") or "Pull-Up / Chin-Up"
    bar_meta = set_metrics.get("bar_reference", {})
    bar_y_norm = bar_meta.get("bar_y_norm", 0.15)
    bar_y_px = int(bar_y_norm * out_h)

    # Re-index reps_data relative to active start frame
    adj_reps_data = []
    for r in reps_data:
        rc = dict(r)
        rc["start_idx"] = max(0, r.get("start_idx", 0) - start_frame)
        rc["end_idx"] = max(0, r.get("end_idx", 0) - start_frame)
        rc["peak_idx"] = max(0, r.get("peak_idx", 0) - start_frame)
        adj_reps_data.append(rc)

    # Build exact exercise trajectory array for synchronized PIP
    raw_traj, smooth_traj, torso_norm = extract_exercise_trajectory(
        frame_data, exercise_name=exercise_name, bar_y_norm=bar_y_norm
    )
    if len(smooth_traj) > 0:
        traj_arr = smooth_traj[start_frame:end_frame + 1]
    else:
        traj_arr = np.zeros(max(1, active_len))

    written_count = 0
    read_idx = -1
    source_frame = None
    def abort_render(message):
        cap.release()
        if ffmpeg_proc:
            ffmpeg_proc.kill()
            ffmpeg_proc.communicate()
        if writer:
            writer.release()
        raise ValueError(message)

    for source_idx, pose_idx in schedule:
        while read_idx < source_idx:
            if not cap.grab():
                abort_render(f"Video ended before source frame {source_idx}")
            read_idx += 1
            if read_idx == source_idx:
                ret, source_frame = cap.retrieve()
                if not ret:
                    abort_render(f"Cannot retrieve source frame {source_idx}")
        # Draw on a copy because the encoding clock may repeat a selected image.
        frame = source_frame.copy()
        frame_idx = pose_idx - start_frame

        if scale < 1.0:
            frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)

        fd = sliced_frames[frame_idx] if frame_idx < len(sliced_frames) else {}
        display_lm = fd.get("display_landmarks", fd.get("filtered_landmarks", fd.get("landmarks", {})))

        # 1. Draw static pull-up bar reference line (if vertical pullup)
        if "pulldown" not in exercise_name.lower() and "row" not in exercise_name.lower():
            cv2.line(frame, (0, bar_y_px), (out_w, bar_y_px), COLOR_BAR, 1, cv2.LINE_AA)
            cv2.putText(
                frame, "BAR REFERENCE", (15, max(20, bar_y_px - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, COLOR_BAR, 1, cv2.LINE_AA
            )

        # 2. Draw confidence-colored skeleton
        _draw_confidence_skeleton(frame, display_lm, out_w, out_h)

        # 3. Determine active rep, completed reps, and phase accurately
        completed_reps = sum(1 for rep in adj_reps_data if rep.get("end_idx", 0) < frame_idx)
        active_rep = None
        for rep in adj_reps_data:
            s_idx = rep.get("start_idx", 0)
            e_idx = rep.get("end_idx", active_len)
            if s_idx <= frame_idx <= e_idx:
                active_rep = rep
                break

        ex_name_lower = exercise_name.lower()

        if active_rep:
            active_rep_num = active_rep.get("rep_number", completed_reps + 1)
            rep_str = f"REP: {active_rep_num}/{total_reps}"
            
            p_idx = active_rep.get("peak_idx", 0)
            if abs(times[pose_idx] - times[start_frame + p_idx]) <= 4 / 30.0 + 1e-7:
                current_phase_name = "PEAK CONTRACTION (HOLD)"
                phase_color = (0, 240, 255)
            elif frame_idx < p_idx:
                if "pulldown" in ex_name_lower:
                    current_phase_name = "CONCENTRIC (PULL DOWN)"
                elif "row" in ex_name_lower:
                    current_phase_name = "CONCENTRIC (ROW DRIVE)"
                else:
                    current_phase_name = "CONCENTRIC (PULL UP)"
                phase_color = (80, 230, 80)
            else:
                if "pulldown" in ex_name_lower:
                    current_phase_name = "ECCENTRIC (RELEASE)"
                elif "row" in ex_name_lower:
                    current_phase_name = "ECCENTRIC (EXTENSION)"
                else:
                    current_phase_name = "ECCENTRIC (LOWER)"
                phase_color = (0, 190, 255)
        else:
            # Not inside an active rep boundary
            if adj_reps_data and frame_idx < adj_reps_data[0].get("start_idx", 0):
                rep_str = f"REP: 0/{total_reps}"
                current_phase_name = "GET READY / START POSITION"
                phase_color = (180, 180, 180)
            elif completed_reps >= total_reps and total_reps > 0:
                rep_str = f"SET COMPLETE: {total_reps}/{total_reps}"
                current_phase_name = "SET FINISHED"
                phase_color = (80, 230, 80)
            else:
                rep_str = f"COMPLETED: {completed_reps}/{total_reps}"
                current_phase_name = "RESET / EXTENSION"
                phase_color = (160, 160, 220)

        # 4. On-Joint Working Bilateral Elbow Flare Overlay
        raw_3d_frames = set_metrics.get("skeleton_3d_frames", [])
        curr_angles = raw_3d_frames[pose_idx].get("angles", {}) if pose_idx < len(raw_3d_frames) else {}
        flare_r_curr = curr_angles.get("elbow_flare_r")
        flare_l_curr = curr_angles.get("elbow_flare_l")

        er_joint = display_lm.get("elbow_r")
        el_joint = display_lm.get("elbow_l")

        if er_joint and len(er_joint) >= 3 and er_joint[2] > 0.40 and flare_r_curr is not None:
            ex_r = int(er_joint[0] * out_w)
            ey_r = int(er_joint[1] * out_h)
            cv2.circle(frame, (ex_r, ey_r), 4, (255, 200, 0), -1)
            cv2.putText(
                frame, f"R: {flare_r_curr:.0f}deg",
                (min(out_w - 90, ex_r + 8), max(22, ey_r - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 220, 50), 1, cv2.LINE_AA
            )

        if el_joint and len(el_joint) >= 3 and el_joint[2] > 0.40 and flare_l_curr is not None:
            ex_l = int(el_joint[0] * out_w)
            ey_l = int(el_joint[1] * out_h)
            cv2.circle(frame, (ex_l, ey_l), 4, (80, 230, 120), -1)
            cv2.putText(
                frame, f"L: {flare_l_curr:.0f}deg",
                (min(out_w - 90, ex_l + 8), max(22, ey_l - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (80, 230, 120), 1, cv2.LINE_AA
            )

        # 5. Top-Left HUD (In-place slice blending to save RAM)
        hud_w, hud_h = max(0, min(330, out_w - 30)), min(112, max(0, out_h - 30))
        hx1, hy1 = 15, 15
        hx2, hy2 = hx1 + hud_w, hy1 + hud_h
        if hx2 > hx1 and hy2 > hy1 and hx2 <= out_w and hy2 <= out_h:
            sub_hud = frame[hy1:hy2, hx1:hx2]
            rect = np.full_like(sub_hud, COLOR_HUD_BG)
            cv2.addWeighted(rect, 0.85, sub_hud, 0.15, 0, sub_hud)
            frame[hy1:hy2, hx1:hx2] = sub_hud
        if hud_w >= 100 and hud_h >= 50:
            cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), (60, 60, 60), 1)
            cv2.putText(frame, rep_str, (30, min(44, hy2 - 32)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"PHASE: {current_phase_name}", (30, min(68, hy2 - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, phase_color, 1, cv2.LINE_AA)

            asym = set_metrics.get("asymmetry_analysis")
            if asym and hud_h >= 90:
                sym_score = asym.get("overall_symmetry_score", 100)
                if sym_score >= 88:
                    sym_col = (80, 230, 80)
                    sym_label = "BALANCED"
                elif sym_score >= 72:
                    sym_col = (0, 190, 255)
                    sym_label = "MILD ASYM"
                else:
                    sym_col = (80, 80, 240)
                    sym_label = "IMBALANCE"
                cv2.putText(frame, f"SYMMETRY: {sym_score}% ({sym_label})", (30, min(94, hy2 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.36, sym_col, 1, cv2.LINE_AA)

        # 6. Synchronized PIP Dashboard
        _render_pip_dashboard(frame, frame_idx, active_len, traj_arr, adj_reps_data, out_w, out_h)

        if ffmpeg_proc and ffmpeg_proc.stdin:
            try:
                ffmpeg_proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, IOError) as write_err:
                print(f"Warning: FFmpeg stdin pipe write error: {write_err}")
                break
        elif writer:
            writer.write(frame)

        written_count += 1

    cap.release()

    # Finalize single-pass FFmpeg encoding
    if ffmpeg_proc:
        try:
            _, stderr = ffmpeg_proc.communicate()
            if ffmpeg_proc.returncode == 0 and os.path.exists(output_path):
                print(f"Single-pass H.264 video rendering complete: {output_path}")
                return output_path
            else:
                err_text = stderr.decode(errors='replace') if stderr else "Unknown error"
                print(f"FFmpeg stdin pipe exited with code {ffmpeg_proc.returncode}: {err_text}")
        except Exception as ffmpeg_pipe_err:
            print(f"Error finalizing FFmpeg pipe: {ffmpeg_pipe_err}")

    # Fallback to secondary re-encode if VideoWriter was used
    if writer:
        writer.release()
        try:
            import subprocess
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            ffmpeg_cmd = [
                ffmpeg_bin, '-y', '-i', temp_render,
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                '-movflags', '+faststart', '-pix_fmt', 'yuv420p', output_path
            ]
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"Fallback H.264 video rendering complete: {output_path}")
            else:
                import shutil
                shutil.copyfile(temp_render, output_path)
        except Exception as fallback_err:
            print(f"Fallback encoding error: {fallback_err}")
            if temp_render and os.path.exists(temp_render):
                import shutil
                shutil.copyfile(temp_render, output_path)

        if temp_render and os.path.exists(temp_render):
            try:
                os.remove(temp_render)
            except Exception:
                pass

    return output_path
