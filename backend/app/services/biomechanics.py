import math
import numpy as np
from app.services.video_timing import frame_times
from typing import List, Dict, Any, Tuple, Optional
from app.services.vbt_calculator import (
    calculate_spatial_scale_meters,
    calculate_rep_velocities,
    estimate_rpe_and_rir
)


def calculate_estimated_3d_elbow_flexion(
    shoulder_3d: Optional[List[float]],
    elbow_3d: Optional[List[float]],
    wrist_3d: Optional[List[float]]
) -> Tuple[Optional[float], float]:
    """
    Computes Estimated 3D Elbow Flexion Angle (in degrees) using 3D metric world coordinates.
    Formula: arccos( (S - E) . (W - E) / (|S - E| * |W - E|) )
    Returns: (estimated_angle_deg, confidence)
    """
    if not shoulder_3d or not elbow_3d or not wrist_3d:
        return None, 0.0

    s = np.array(shoulder_3d[:3], dtype=float)
    e = np.array(elbow_3d[:3], dtype=float)
    w = np.array(wrist_3d[:3], dtype=float)

    conf_s = shoulder_3d[3] if len(shoulder_3d) > 3 else 1.0
    conf_e = elbow_3d[3] if len(elbow_3d) > 3 else 1.0
    conf_w = wrist_3d[3] if len(wrist_3d) > 3 else 1.0
    meas_conf = float(min(conf_s, conf_e, conf_w))

    if meas_conf < 0.35:
        return None, meas_conf

    v1 = s - e
    v2 = w - e
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)

    if norm_v1 == 0 or norm_v2 == 0:
        return None, 0.0

    cos_val = np.dot(v1, v2) / (norm_v1 * norm_v2)
    angle_rad = np.arccos(np.clip(cos_val, -1.0, 1.0))
    angle_deg = float(np.degrees(angle_rad))
    return angle_deg, meas_conf


def calculate_estimated_3d_elbow_flare(
    shoulder_l: Optional[List[float]],
    shoulder_r: Optional[List[float]],
    hip_working: Optional[List[float]],
    elbow_working: Optional[List[float]]
) -> Tuple[Optional[float], float]:
    """
    Calculates Estimated 3D Shoulder Abduction / Elbow Flare relative to the torso plane.
    """
    if not shoulder_l or not shoulder_r or not hip_working or not elbow_working:
        return None, 0.0

    sl = np.array(shoulder_l[:3], dtype=float)
    sr = np.array(shoulder_r[:3], dtype=float)
    h = np.array(hip_working[:3], dtype=float)
    e = np.array(elbow_working[:3], dtype=float)

    conf_sl = shoulder_l[3] if len(shoulder_l) > 3 else 1.0
    conf_sr = shoulder_r[3] if len(shoulder_r) > 3 else 1.0
    conf_h = hip_working[3] if len(hip_working) > 3 else 1.0
    conf_e = elbow_working[3] if len(elbow_working) > 3 else 1.0
    meas_conf = float(min(conf_sl, conf_sr, conf_h, conf_e))

    if meas_conf < 0.35:
        return None, meas_conf

    # Coronal plane lateral axis
    lateral_vec = sl[:2] - sr[:2]
    norm_lat = np.linalg.norm(lateral_vec)
    if norm_lat == 0:
        return None, 0.0
    lateral_vec = lateral_vec / norm_lat

    # Torso vertical axis
    torso_vec = h[:2] - sr[:2]
    norm_torso = np.linalg.norm(torso_vec)
    if norm_torso == 0:
        return None, 0.0
    torso_vec = torso_vec / norm_torso

    # Orthogonalize
    torso_vec = torso_vec - np.dot(torso_vec, lateral_vec) * lateral_vec
    norm_t2 = np.linalg.norm(torso_vec)
    if norm_t2 == 0:
        return None, 0.0
    torso_vec = torso_vec / norm_t2

    # Humerus vector
    humerus_vec = e[:2] - sr[:2]
    lat_comp = np.dot(humerus_vec, lateral_vec)
    vert_comp = np.dot(humerus_vec, torso_vec)

    flare_rad = np.arctan2(abs(lat_comp), max(1e-4, vert_comp))
    return float(np.degrees(flare_rad)), meas_conf


def _compute_rep_bilateral_kinematics(
    start_idx: int,
    peak_idx: int,
    end_idx: int,
    elbow_flares_r: List[Optional[float]],
    elbow_flares_l: List[Optional[float]],
    shoulder_tilts_deg: List[float],
    shoulder_elevated_sides: List[str],
    timestamps_s: Optional[List[float]] = None
) -> Dict[str, Any]:
    """Computes bilateral elbow flare and shoulder elevation tilt for a single rep."""
    flares_r_seg = [f for f in elbow_flares_r[start_idx:end_idx] if f is not None]
    flares_l_seg = [f for f in elbow_flares_l[start_idx:end_idx] if f is not None]
    avg_f_r = float(np.mean(flares_r_seg)) if flares_r_seg else 70.0
    avg_f_l = float(np.mean(flares_l_seg)) if flares_l_seg else 70.0
    avg_f = float(np.mean(flares_r_seg + flares_l_seg)) if (flares_r_seg or flares_l_seg) else 70.0

    # Peak window (around peak pull where asymmetry is mechanically most pronounced)
    w_start = max(start_idx, peak_idx - 5)
    w_end = min(end_idx, peak_idx + 6)
    if timestamps_s is not None:
        peak_time = timestamps_s[peak_idx]
        w_start = max(start_idx, int(np.searchsorted(timestamps_s, peak_time - 5 / 30.0 - 1e-7)))
        w_end = min(end_idx, int(np.searchsorted(timestamps_s, peak_time + 5 / 30.0 + 1e-7, side="right")))
    tilts_seg = [t for t in shoulder_tilts_deg[w_start:w_end] if t is not None]
    avg_tilt = float(np.mean(tilts_seg)) if tilts_seg else 0.0

    sides_seg = shoulder_elevated_sides[w_start:w_end]
    non_bal = [s for s in sides_seg if s != "Balanced"]
    elev_side = max(set(non_bal), key=non_bal.count) if non_bal else "Balanced"

    return {
        "contraction_flare": avg_f,
        "right_flare": avg_f_r,
        "left_flare": avg_f_l,
        "shoulder_tilt_deg": avg_tilt,
        "elevated_shoulder_side": elev_side
    }


def detect_static_bar_reference(frame_data: List[Dict[str, Any]]) -> Tuple[float, float, bool]:
    """
    Detects static scene pull-up bar / grip anchor line from top wrist positions.
    Returns: (bar_y_norm, bar_tilt_deg, is_detected)
    """
    wrist_y_positions = []
    wrist_tilts = []

    times = frame_times(frame_data)
    for i, fd in enumerate(frame_data):  # First second, independent of sampling cadence
        if times[i] >= times[0] + 1.0 - 1e-7:
            break
        lm = fd.get("filtered_landmarks", fd.get("landmarks", {}))
        wr = lm.get("wrist_r")
        wl = lm.get("wrist_l")
        if wr and wl:
            y_avg = (wr[1] + wl[1]) / 2.0
            wrist_y_positions.append(y_avg)
            dx = wl[0] - wr[0]
            dy = wl[1] - wr[1]
            if abs(dx) > 0.05:
                wrist_tilts.append(np.degrees(np.arctan2(dy, dx)))

    if wrist_y_positions:
        bar_y = float(np.median(wrist_y_positions))
        bar_tilt = float(np.median(wrist_tilts)) if wrist_tilts else 0.0
        return bar_y, bar_tilt, True
    return 0.15, 0.0, False


def smooth_kinematic_signal(signal: np.ndarray, window_size: int = 7) -> np.ndarray:
    """
    Applies zero-phase smoothing to suppress high-frequency MediaPipe landmark jitter
    while strictly preserving true peak and valley inflection timings.
    """
    if len(signal) < window_size:
        return signal
    window_size = min(window_size, len(signal))
    if window_size % 2 == 0:
        window_size += 1
    kernel = np.ones(window_size) / window_size
    pad_len = window_size // 2
    padded = np.pad(signal, (pad_len, pad_len), mode='edge')
    smoothed = np.convolve(padded, kernel, mode='valid')
    return smoothed[:len(signal)]


def extract_exercise_trajectory(
    frame_data: List[Dict[str, Any]],
    exercise_name: str = "Pull-Up / Chin-Up",
    bar_y_norm: float = 0.15
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Extracts the primary biomechanical contraction trajectory tailored to the exercise modality.
    Returns: (raw_trajectory, smoothed_trajectory, avg_torso_length)
    """
    n_frames = len(frame_data)
    trajectory = []
    torso_lengths = []
    ex_lower = (exercise_name or "").lower()

    for fd in frame_data:
        lm = fd.get("filtered_landmarks", fd.get("landmarks", {}))
        sr = lm.get("shoulder_r")
        sl = lm.get("shoulder_l")
        hr = lm.get("hip_r")
        hl = lm.get("hip_l")
        er = lm.get("elbow_r")
        el = lm.get("elbow_l")
        wr = lm.get("wrist_r")
        wl = lm.get("wrist_l")

        # Torso length reference
        if sr and sl and hr and hl:
            mid_s = np.array([(sr[0] + sl[0]) / 2.0, (sr[1] + sl[1]) / 2.0])
            mid_h = np.array([(hr[0] + hl[0]) / 2.0, (hr[1] + hl[1]) / 2.0])
            torso_lengths.append(float(np.linalg.norm(mid_s - mid_h)))

        # MODALITY 1: Lat Pulldown (Wrist pulled DOWN toward shoulders/chest)
        if "pulldown" in ex_lower:
            if wr and wl and sr and sl:
                wrist_y = (wr[1] + wl[1]) / 2.0
                shoulder_y = (sr[1] + sl[1]) / 2.0
                # When pulled down, wrist_y increases towards/below shoulder_y
                # Contraction increases as (wrist_y - shoulder_y) increases
                disp = wrist_y - shoulder_y
                trajectory.append(disp)
            elif wr and sr:
                trajectory.append(wr[1] - sr[1])
            elif wl and sl:
                trajectory.append(wl[1] - sl[1])
            else:
                trajectory.append(trajectory[-1] if trajectory else 0.0)

        # MODALITY 2: Horizontal Rows (Barbell Row, Cable Row, Dumbbell Row)
        elif "row" in ex_lower:
            # For rows, contraction is measured by elbow retraction past hip/shoulder
            if er and el and sr and sl:
                # Relative distance of elbows to hips/torso plane
                elbow_x = (er[0] + el[0]) / 2.0
                wrist_x = (wr[0] + wl[0]) / 2.0 if (wr and wl) else elbow_x
                elbow_y = (er[1] + el[1]) / 2.0
                shoulder_y = (sr[1] + sl[1]) / 2.0
                # Composite retraction travel
                retraction = np.linalg.norm([elbow_x - wrist_x, elbow_y - shoulder_y])
                trajectory.append(float(retraction))
            elif er and sr:
                trajectory.append(float(abs(er[1] - sr[1])))
            else:
                trajectory.append(trajectory[-1] if trajectory else 0.0)

        # MODALITY 3: Bodyweight Pull-Up / Chin-Up (Shoulders pulled UP toward fixed bar)
        else:
            if sr and sl:
                mid_s_y = (sr[1] + sl[1]) / 2.0
                # As lifter pulls up, mid_s_y decreases towards bar_y_norm.
                # Contraction height is positive upwards: (bar_y_norm - mid_s_y) or (1.0 - mid_s_y)
                trajectory.append(bar_y_norm - mid_s_y)
            elif sr:
                trajectory.append(bar_y_norm - sr[1])
            elif sl:
                trajectory.append(bar_y_norm - sl[1])
            else:
                trajectory.append(trajectory[-1] if trajectory else 0.0)

    avg_torso = float(np.median(torso_lengths)) if torso_lengths else 0.35
    raw_arr = np.array(trajectory, dtype=float)
    times = np.array(frame_times(frame_data))
    finite_mask = np.isfinite(raw_arr)
    if len(raw_arr) and not np.all(finite_mask):
        if np.any(finite_mask):
            valid_idx = np.flatnonzero(finite_mask)
            raw_arr = np.interp(times, times[valid_idx], raw_arr[finite_mask])
        else:
            raw_arr = np.zeros_like(raw_arr)
    # Preserve the original seven-point / 30 FPS smoothing duration at any cadence.
    # Interpolate positions only for signal smoothing, never missing measurement joints.
    smooth_arr = raw_arr.copy()
    if len(raw_arr) >= 2 and times[-1] - times[0] >= 6 / 30.0 - 1e-7:
        smooth_arr = np.mean([
            np.interp(times + offset / 30.0, times, raw_arr)
            for offset in range(-3, 4)
        ], axis=0)

    return raw_arr, smooth_arr, avg_torso


def analyze_set(
    frame_data: List[Dict[str, Any]],
    fps: float = 30.0,
    user_height_cm: Optional[float] = None,
    exercise_name: str = "Pull-Up / Chin-Up"
) -> Dict[str, Any]:
    """
    Comprehensive Biomechanical Kinematics & Hysteresis Repetition Segmentation Engine.
    Tailors kinematic trajectory tracking and zero-crossing FSM to the exact exercise modality.
    """
    if not frame_data:
        return {
            "total_reps": 0,
            "full_reps": 0,
            "partial_reps": 0,
            "reps_data": [],
            "vbt_summary": {"velocity_loss_available": False, "estimated_rpe": 0.0, "estimated_rir": 0}
        }

    n_frames = len(frame_data)
    safe_fps = fps if fps and fps > 0 else 30.0
    timestamps_s = frame_times(frame_data, safe_fps)
    # Give every consumer the same repaired timeline without mutating callers.
    frame_data = [dict(fd, timestamp_s=t) for fd, t in zip(frame_data, timestamps_s)]

    # 1. Detect static bar reference (for vertical pull-ups)
    bar_y_norm, bar_tilt_deg, bar_detected = detect_static_bar_reference(frame_data)

    # 2. Extract exercise-specific trajectory
    raw_traj, smooth_traj, avg_torso_norm = extract_exercise_trajectory(
        frame_data, exercise_name=exercise_name, bar_y_norm=bar_y_norm
    )

    # Dynamic baseline dynamic range
    traj_min = float(np.percentile(smooth_traj, 5))
    traj_max = float(np.percentile(smooth_traj, 95))
    dyn_range = max(1e-4, traj_max - traj_min)

    # 3. Extract 3D Joint Kinematics (using 3D World Landmarks)
    elbow_flares_r = []
    elbow_flares_l = []
    elbow_flexions_r = []
    elbow_flexions_l = []
    shoulder_tilts_deg = []
    shoulder_elevated_sides = []

    for fd in frame_data:
        lm_filt = fd.get("filtered_landmarks", fd.get("landmarks", {}))
        lm_world = fd.get("world_landmarks", {}) or {}

        sr_w = lm_world.get("shoulder_r") or lm_filt.get("shoulder_r")
        sl_w = lm_world.get("shoulder_l") or lm_filt.get("shoulder_l")
        hr_w = lm_world.get("hip_r") or lm_filt.get("hip_r")
        hl_w = lm_world.get("hip_l") or lm_filt.get("hip_l")
        er_w = lm_world.get("elbow_r") or lm_filt.get("elbow_r")
        el_w = lm_world.get("elbow_l") or lm_filt.get("elbow_l")
        wr_w = lm_world.get("wrist_r") or lm_filt.get("wrist_r")
        wl_w = lm_world.get("wrist_l") or lm_filt.get("wrist_l")

        flex_r, _ = calculate_estimated_3d_elbow_flexion(sr_w, er_w, wr_w)
        flex_l, _ = calculate_estimated_3d_elbow_flexion(sl_w, el_w, wl_w)
        elbow_flexions_r.append(flex_r)
        elbow_flexions_l.append(flex_l)

        flare_r, _ = calculate_estimated_3d_elbow_flare(sl_w, sr_w, hr_w, er_w)
        flare_l, _ = calculate_estimated_3d_elbow_flare(sr_w, sl_w, hl_w, el_w)
        elbow_flares_r.append(flare_r)
        elbow_flares_l.append(flare_l)

        # Bilateral shoulder line tilt (degrees from horizontal)
        if sr_w and sl_w and len(sr_w) >= 2 and len(sl_w) >= 2:
            dx = abs(float(sr_w[0]) - float(sl_w[0]))
            dy = float(sr_w[1]) - float(sl_w[1])
            tilt_angle = float(np.degrees(np.arctan2(abs(dy), max(1e-4, dx))))
            # In MediaPipe image/world landmarks, lower Y is higher elevation (toward head)
            elev_side = "Right" if dy < -0.015 else ("Left" if dy > 0.015 else "Balanced")
        else:
            tilt_angle = 0.0
            elev_side = "Balanced"
        shoulder_tilts_deg.append(tilt_angle)
        shoulder_elevated_sides.append(elev_side)

    # 4. Hysteresis-Gated Finite State Machine (FSM)
    # States: IDLE_START (0) -> CONCENTRIC_DRIVE (1) -> PEAK_CONTRACTION (2) -> ECCENTRIC_LOWER (3)
    MIN_CONC_TIME_S = 0.18
    MIN_ECC_TIME_S = 0.18
    MIN_CONC_TRAVEL = max(0.04, 0.22 * dyn_range)

    raw_reps = []
    state = 0
    conc_start_idx = 0
    peak_idx = 0
    state_enter_time = timestamps_s[0]
    min_valley_val = smooth_traj[0]

    for i in range(1, n_frames - 1):
        t_curr = timestamps_s[i]
        dt_state = t_curr - state_enter_time
        
        # Central difference velocity on smoothed signal
        dt_frame = max(1e-4, timestamps_s[i] - timestamps_s[i - 1])
        d_vel = (smooth_traj[i] - smooth_traj[i - 1]) / dt_frame

        if state == 0:  # IDLE / VALLEY START
            if smooth_traj[i] < min_valley_val:
                min_valley_val = smooth_traj[i]
                conc_start_idx = i

            # Concentric trigger: positive velocity and upward departure from valley
            if d_vel > 0.04 and (smooth_traj[i] - min_valley_val) >= (0.10 * dyn_range):
                state = 1
                state_enter_time = t_curr

        elif state == 1:  # CONCENTRIC DRIVE
            # Check for peak turnaround: velocity drops to <= 0 with adequate displacement & time
            if (d_vel <= 0.0 or i == n_frames - 2) and dt_state >= MIN_CONC_TIME_S:
                conc_disp = smooth_traj[i] - smooth_traj[conc_start_idx]
                if conc_disp >= MIN_CONC_TRAVEL:
                    state = 2  # PEAK
                    peak_idx = i
                    state_enter_time = t_curr
                else:
                    # Minor false departure: return to valley tracking
                    state = 0
                    min_valley_val = smooth_traj[i]
                    conc_start_idx = i
                    state_enter_time = t_curr

        elif state == 2:  # PEAK CONTRACTION / ISOMETRIC
            # Transition to eccentric when velocity turns decisively negative
            if d_vel < -0.03 and dt_state >= 0.06:
                state = 3  # ECCENTRIC
                state_enter_time = t_curr

        elif state == 3:  # ECCENTRIC CONTROL
            conc_travel = abs(smooth_traj[peak_idx] - smooth_traj[conc_start_idx])
            ecc_travel = abs(smooth_traj[peak_idx] - smooth_traj[i])

            # Transition when true eccentric bottom inflection occurs, deep return is reached, or end of video
            is_end_of_video = (i >= n_frames - 2)
            has_meaningful_eccentric = (ecc_travel >= 0.35 * conc_travel) or (ecc_travel >= MIN_CONC_TRAVEL)
            is_valley_inflection = (d_vel >= 0.02 and has_meaningful_eccentric)
            is_deep_return = (smooth_traj[i] <= smooth_traj[conc_start_idx] + 0.25 * conc_travel)

            if (is_valley_inflection or is_deep_return or is_end_of_video) and dt_state >= MIN_ECC_TIME_S:
                ecc_end_idx = i
                conc_time = timestamps_s[peak_idx] - timestamps_s[conc_start_idx]
                ecc_time = timestamps_s[ecc_end_idx] - timestamps_s[peak_idx]

                if conc_travel >= MIN_CONC_TRAVEL and ecc_travel >= (0.35 * MIN_CONC_TRAVEL):
                    bilat_k = _compute_rep_bilateral_kinematics(
                        conc_start_idx, peak_idx, ecc_end_idx,
                        elbow_flares_r, elbow_flares_l,
                        shoulder_tilts_deg, shoulder_elevated_sides, timestamps_s
                    )

                    raw_reps.append({
                        "start_idx": conc_start_idx,
                        "peak_idx": peak_idx,
                        "end_idx": ecc_end_idx,
                        "concentric_tempo": conc_time,
                        "eccentric_tempo": ecc_time,
                        "concentric_travel": conc_travel,
                        "eccentric_travel": ecc_travel,
                        "contraction_flare": bilat_k["contraction_flare"],
                        "right_flare": bilat_k["right_flare"],
                        "left_flare": bilat_k["left_flare"],
                        "shoulder_tilt_deg": bilat_k["shoulder_tilt_deg"],
                        "elevated_shoulder_side": bilat_k["elevated_shoulder_side"]
                    })

                state = 0
                conc_start_idx = i
                min_valley_val = smooth_traj[i]
                state_enter_time = t_curr

    # Fallback to peak-finder if FSM found 0 reps
    if not raw_reps:
        from scipy.signal import find_peaks
        def timed_peaks(signal):
            indices, _ = find_peaks(signal, prominence=0.03)
            selected = []
            for idx in sorted(indices, key=lambda i: signal[i], reverse=True):
                if all(abs(timestamps_s[idx] - timestamps_s[j]) >= 0.4 - 1e-7 for j in selected):
                    selected.append(idx)
            return sorted(selected)

        peaks = timed_peaks(smooth_traj)
        valleys = timed_peaks(-smooth_traj)
        for j in range(len(peaks)):
            p = peaks[j]
            before = max(0, int(np.searchsorted(timestamps_s, timestamps_s[p] - 1.0)))
            after = min(n_frames - 1, int(np.searchsorted(timestamps_s, timestamps_s[p] + 1.0)))
            v_before = max([v for v in valleys if v < p], default=before)
            v_after = min([v for v in valleys if v > p], default=after)
            conc_travel = abs(smooth_traj[p] - smooth_traj[v_before])
            ecc_travel = abs(smooth_traj[p] - smooth_traj[v_after])
            if conc_travel < MIN_CONC_TRAVEL or ecc_travel < (0.4 * MIN_CONC_TRAVEL):
                continue
            c_time = max(0.2, timestamps_s[p] - timestamps_s[v_before])
            e_time = max(0.2, timestamps_s[v_after] - timestamps_s[p])
            bilat_k = _compute_rep_bilateral_kinematics(
                v_before, p, v_after,
                elbow_flares_r, elbow_flares_l,
                shoulder_tilts_deg, shoulder_elevated_sides, timestamps_s
            )
            raw_reps.append({
                "start_idx": v_before,
                "peak_idx": p,
                "end_idx": v_after,
                "concentric_tempo": c_time,
                "eccentric_tempo": e_time,
                "concentric_travel": conc_travel,
                "eccentric_travel": ecc_travel,
                "contraction_flare": bilat_k["contraction_flare"],
                "right_flare": bilat_k["right_flare"],
                "left_flare": bilat_k["left_flare"],
                "shoulder_tilt_deg": bilat_k["shoulder_tilt_deg"],
                "elevated_shoulder_side": bilat_k["elevated_shoulder_side"]
            })

    # 4. Multi-Segment Anthropometric Scale Calibration & VBT Velocities
    scale_m_per_coord, scale_confidence_desc = calculate_spatial_scale_meters(
        frame_data, user_height_cm=user_height_cm
    )
    vbt_reps = calculate_rep_velocities(raw_reps, scale_m_per_coord)

    max_conc = max((r["concentric_travel"] for r in raw_reps), default=1.0) or 1.0
    max_ecc = max((r["eccentric_travel"] for r in raw_reps), default=1.0) or 1.0

    rom_percentages = [round((r["concentric_travel"] / max_conc) * 100, 1) for r in raw_reps]

    final_reps = []
    for idx, r in enumerate(raw_reps):
        conc_rom = float(rom_percentages[idx])
        ecc_rom = float(round((r["eccentric_travel"] / max_ecc) * 100, 1))

        # Two-Tier ROM Validity: rep is full if concentric ROM >= 70%
        is_partial = bool(conc_rom < 70.0)
        v_info = vbt_reps[idx] if idx < len(vbt_reps) else {"mean_velocity_mps": 0.0, "peak_velocity_mps": 0.0}

        # Intentional partial vs early technique flaw
        is_intentional = bool(is_partial and idx == len(raw_reps) - 1 and idx > 0)
        is_flaw = bool(is_partial and not is_intentional)

        f_r = float(round(r.get("right_flare", 70.0), 1))
        f_l = float(round(r.get("left_flare", 70.0), 1))
        flare_delta = float(round(abs(f_r - f_l), 1))
        dominant_side = "Right" if f_r > f_l + 1.5 else ("Left" if f_l > f_r + 1.5 else "Balanced")
        tilt_deg = float(round(r.get("shoulder_tilt_deg", 0.0), 1))
        elev_side = r.get("elevated_shoulder_side", "Balanced")

        # Rep symmetry score: 100 - penalties
        flare_pen = max(0.0, (flare_delta - 5.0) * 2.5)
        tilt_pen = max(0.0, (tilt_deg - 3.0) * 3.0)
        rep_sym_score = max(40, min(100, int(round(100.0 - flare_pen - tilt_pen))))

        if flare_delta <= 5.0 and tilt_deg <= 3.5:
            asym_status = "balanced"
        elif flare_delta <= 12.0 and tilt_deg <= 6.5:
            asym_status = "mild"
        else:
            asym_status = "significant"

        final_reps.append({
            "rep_number": int(idx + 1),
            "start_idx": int(r["start_idx"]),
            "peak_idx": int(r["peak_idx"]),
            "end_idx": int(r["end_idx"]),
            "contraction_elbow_flare_degrees": float(round(r["contraction_flare"], 1)),
            "left_elbow_flare_deg": f_l,
            "right_elbow_flare_deg": f_r,
            "elbow_flare_delta_deg": flare_delta,
            "dominant_flare_side": dominant_side,
            "shoulder_tilt_deg": tilt_deg,
            "elevated_shoulder_side": elev_side,
            "asymmetry_status": asym_status,
            "rep_symmetry_score": rep_sym_score,
            "eccentric_tempo_s": float(round(r["eccentric_tempo"], 2)),
            "concentric_tempo_s": float(round(r["concentric_tempo"], 2)),
            "mean_velocity_mps": float(v_info["mean_velocity_mps"]),
            "peak_velocity_mps": float(v_info["peak_velocity_mps"]),
            "concentric_rom_pct": float(conc_rom),
            "eccentric_rom_pct": float(ecc_rom),
            "rom_percentage": float(conc_rom),
            "is_partial_rep": is_partial,
            "is_intentional_partial": is_intentional,
            "is_technique_flaw": is_flaw
        })

    rpe, rir, vl_pct, vl_available, vl_reason_code, vl_explanation = estimate_rpe_and_rir(
        vbt_reps, rom_percentages
    )
    avg_vel = float(np.mean([v["mean_velocity_mps"] for v in vbt_reps])) if vbt_reps else 0.0

    # Calculate Set-Level Bilateral Asymmetry & Imbalance Analysis
    if final_reps:
        avg_flare_delta = float(round(np.mean([r["elbow_flare_delta_deg"] for r in final_reps]), 1))
        max_flare_delta = float(round(max(r["elbow_flare_delta_deg"] for r in final_reps), 1))
        avg_shoulder_tilt = float(round(np.mean([r["shoulder_tilt_deg"] for r in final_reps]), 1))
        overall_sym_score = int(round(np.mean([r["rep_symmetry_score"] for r in final_reps])))

        avg_f_l = float(round(np.mean([r["left_elbow_flare_deg"] for r in final_reps]), 1))
        avg_f_r = float(round(np.mean([r["right_elbow_flare_deg"] for r in final_reps]), 1))

        if overall_sym_score >= 88 and avg_flare_delta <= 5.5:
            classification = "Symmetrical & Balanced"
        elif overall_sym_score >= 72 and avg_flare_delta <= 12.0:
            classification = "Mild Asymmetry"
        else:
            classification = "Significant Imbalance Detected"

        # Fatigue drift detection (asymmetry escalating in 2nd half of set)
        fatigue_drift = False
        if len(final_reps) >= 4:
            mid = len(final_reps) // 2
            first_half_delta = float(np.mean([r["elbow_flare_delta_deg"] for r in final_reps[:mid]]))
            second_half_delta = float(np.mean([r["elbow_flare_delta_deg"] for r in final_reps[mid:]]))
            if second_half_delta > (first_half_delta + 4.0) and second_half_delta > 7.0:
                fatigue_drift = True

        # Primary pattern diagnostic
        r_tilts = [r for r in final_reps if r["elevated_shoulder_side"] == "Right" and r["shoulder_tilt_deg"] > 3.5]
        l_tilts = [r for r in final_reps if r["elevated_shoulder_side"] == "Left" and r["shoulder_tilt_deg"] > 3.5]

        if avg_f_r > avg_f_l + 6.0:
            primary_pattern = "Right Arm Flaring Excessively"
            pattern_desc = f"Right elbow flared {avg_f_r - avg_f_l:.1f}° wider than left on average, suggesting right lat disengagement and upper-trap/rotator compensation."
        elif avg_f_l > avg_f_r + 6.0:
            primary_pattern = "Left Arm Flaring Excessively"
            pattern_desc = f"Left elbow flared {avg_f_l - avg_f_r:.1f}° wider than right on average, indicating non-dominant lat fatigue or dominant right-side pulling bias."
        elif len(r_tilts) >= max(1, len(final_reps) // 2):
            primary_pattern = "Right Shoulder Hiking / Trap Compensation"
            pattern_desc = "Right shoulder consistently elevated during peak contraction, indicating unilateral upper-trap shrugging."
        elif len(l_tilts) >= max(1, len(final_reps) // 2):
            primary_pattern = "Left Shoulder Hiking / Trap Compensation"
            pattern_desc = "Left shoulder consistently elevated during peak contraction, indicating unilateral upper-trap shrugging."
        elif fatigue_drift:
            primary_pattern = "Fatigue-Induced Late-Set Asymmetry"
            pattern_desc = "Bilateral symmetry was clean in early reps but broke down significantly as fatigue accumulated in later reps."
        else:
            primary_pattern = "Balanced Bilateral Mechanics"
            pattern_desc = f"Both arms moved with uniform symmetry ({avg_flare_delta}° average delta) and consistent shoulder depression."

        corrective_cues = []
        if "Right Arm Flaring" in primary_pattern:
            corrective_cues.append("Focus on pulling the right elbow down toward your hip/pocket to engage the right lower lat.")
            corrective_cues.append("Incorporate unilateral single-arm pulldowns or single-arm dumbbell rows to balance lat recruitment.")
        elif "Left Arm Flaring" in primary_pattern:
            corrective_cues.append("Focus on pulling the left elbow down toward your hip/pocket to engage the left lower lat.")
            corrective_cues.append("Incorporate unilateral single-arm pulldowns or single-arm dumbbell rows to strengthen the non-dominant lat.")
        elif "Shoulder Hiking" in primary_pattern:
            corrective_cues.append("Actively depress both scapulae before initiating the pull; avoid shrugging upward at peak contraction.")
            corrective_cues.append("Check grip width to ensure hands are placed equidistant from the center.")
        elif fatigue_drift:
            corrective_cues.append("Terminate working sets when bilateral asymmetry exceeds 10° to avoid ingraining compensatory motor patterns.")
            corrective_cues.append("Ensure controlled, symmetrical eccentric descent tempo even under heavy fatigue.")
        else:
            corrective_cues.append("Maintain current symmetrical pull mechanics.")
            corrective_cues.append("Ensure grip width remains identical relative to barbell/handle markings.")

        asymmetry_analysis = {
            "overall_symmetry_score": overall_sym_score,
            "asymmetry_classification": classification,
            "avg_flare_delta_deg": avg_flare_delta,
            "max_flare_delta_deg": max_flare_delta,
            "avg_shoulder_tilt_deg": avg_shoulder_tilt,
            "mean_left_flare_deg": avg_f_l,
            "mean_right_flare_deg": avg_f_r,
            "primary_pattern": primary_pattern,
            "pattern_description": pattern_desc,
            "fatigue_drift_detected": fatigue_drift,
            "corrective_cues": corrective_cues,
            "heatmap_rows": [
                {
                    "rep_number": r["rep_number"],
                    "left_flare_deg": r["left_elbow_flare_deg"],
                    "right_flare_deg": r["right_elbow_flare_deg"],
                    "flare_delta_deg": r["elbow_flare_delta_deg"],
                    "dominant_side": r["dominant_flare_side"],
                    "shoulder_tilt_deg": r["shoulder_tilt_deg"],
                    "elevated_side": r["elevated_shoulder_side"],
                    "status": r["asymmetry_status"],
                    "rep_symmetry_score": r["rep_symmetry_score"]
                }
                for r in final_reps
            ]
        }
    else:
        asymmetry_analysis = {
            "overall_symmetry_score": 100,
            "asymmetry_classification": "Symmetrical & Balanced",
            "avg_flare_delta_deg": 0.0,
            "max_flare_delta_deg": 0.0,
            "avg_shoulder_tilt_deg": 0.0,
            "mean_left_flare_deg": 70.0,
            "mean_right_flare_deg": 70.0,
            "primary_pattern": "No reps analyzed",
            "pattern_description": "Insufficient repetition data to compute bilateral asymmetry.",
            "fatigue_drift_detected": False,
            "corrective_cues": [],
            "heatmap_rows": []
        }

    # Pack 3D skeleton frames for interactive Three.js 3D visualizer
    target_3d_joints = [
        "shoulder_r", "elbow_r", "wrist_r",
        "shoulder_l", "elbow_l", "wrist_l",
        "hip_r", "hip_l",
        "knee_r", "knee_l", "ankle_r", "ankle_l"
    ]
    skeleton_3d_frames = []
    for i, fd in enumerate(frame_data):
        lm_world = fd.get("world_landmarks") or {}
        lm_filt = fd.get("display_landmarks") or fd.get("filtered_landmarks") or fd.get("landmarks") or {}
        frame_joints = {}
        for j_name in target_3d_joints:
            pt = lm_world.get(j_name)
            if not pt or len(pt) < 3 or pt[0] is None:
                pt = lm_filt.get(j_name)
            if pt and len(pt) >= 3 and pt[0] is not None:
                frame_joints[j_name] = [round(float(pt[0]), 4), round(float(pt[1]), 4), round(float(pt[2]), 4)]
            else:
                frame_joints[j_name] = None

        flare_r_val = round(float(elbow_flares_r[i]), 1) if (i < len(elbow_flares_r) and elbow_flares_r[i] is not None) else 70.0
        flare_l_val = round(float(elbow_flares_l[i]), 1) if (i < len(elbow_flares_l) and elbow_flares_l[i] is not None) else 70.0
        flex_r_val = round(float(elbow_flexions_r[i]), 1) if (i < len(elbow_flexions_r) and elbow_flexions_r[i] is not None) else 90.0
        flex_l_val = round(float(elbow_flexions_l[i]), 1) if (i < len(elbow_flexions_l) and elbow_flexions_l[i] is not None) else 90.0
        tilt_val = round(float(shoulder_tilts_deg[i]), 1) if (i < len(shoulder_tilts_deg) and shoulder_tilts_deg[i] is not None) else 0.0

        skeleton_3d_frames.append({
            "frame_idx": int(i),
            "timestamp_s": float(round(timestamps_s[i] if i < len(timestamps_s) else i / safe_fps, 3)),
            "joints": frame_joints,
            "angles": {
                "elbow_flare_r": flare_r_val,
                "elbow_flare_l": flare_l_val,
                "elbow_flexion_r": flex_r_val,
                "elbow_flexion_l": flex_l_val,
                "shoulder_tilt": tilt_val
            }
        })

    return {
        "total_reps": int(len(final_reps)),
        "full_reps": int(sum(1 for r in final_reps if not r["is_partial_rep"])),
        "intentional_partials": int(sum(1 for r in final_reps if r["is_intentional_partial"])),
        "technique_flaw_partials": int(sum(1 for r in final_reps if r["is_technique_flaw"])),
        "partial_reps": int(sum(1 for r in final_reps if r["is_partial_rep"])),
        "reps_data": final_reps,
        "skeleton_3d_frames": skeleton_3d_frames,
        "bar_reference": {
            "bar_y_norm": float(bar_y_norm),
            "bar_tilt_deg": float(bar_tilt_deg),
            "bar_detected": bool(bar_detected)
        },
        "scale_calibration": {
            "scale_m_per_coord": float(round(scale_m_per_coord, 3)),
            "scale_confidence": str(scale_confidence_desc)
        },
        "vbt_summary": {
            "avg_concentric_velocity_mps": float(round(avg_vel, 2)),
            "velocity_loss_pct": float(vl_pct),
            "velocity_loss_available": bool(vl_available),
            "velocity_loss_reason_code": str(vl_reason_code),
            "velocity_loss_explanation": str(vl_explanation),
            "estimated_rpe": float(rpe),
            "estimated_rir": int(rir)
        },
        "asymmetry_analysis": asymmetry_analysis
    }
