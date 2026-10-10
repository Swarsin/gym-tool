"""
Velocity-Based Training (VBT) & Anthropometric Scale Calibration Engine.
Calculates metric velocities from image displacements, gates velocity loss
on rep-level ROM comparability, and outputs structured diagnostic reason codes.
"""

import numpy as np
from typing import List, Dict, Any, Tuple, Optional


def calculate_spatial_scale_meters(
    frame_data: List[Dict[str, Any]],
    user_height_cm: Optional[float] = None
) -> Tuple[float, str]:
    """
    Computes meters per normalized 2D coordinate unit using multi-segment biometric scaling.
    If user_height_cm is supplied, anchors scale with MODERATE-HIGH confidence.
    If omitted, reports MODERATE-LOW unanchored anthropometric scale confidence.
    """
    torso_lengths = []
    humerus_lengths = []

    for fd in frame_data:
        lm = fd.get("filtered_landmarks", fd.get("landmarks", {}))
        if not lm:
            continue
        sr = lm.get("shoulder_r")
        sl = lm.get("shoulder_l")
        hr = lm.get("hip_r")
        hl = lm.get("hip_l")
        er = lm.get("elbow_r")
        el = lm.get("elbow_l")

        if sr and sl and hr and hl:
            mid_s = np.array([(sr[0] + sl[0]) / 2.0, (sr[1] + sl[1]) / 2.0])
            mid_h = np.array([(hr[0] + hl[0]) / 2.0, (hr[1] + hl[1]) / 2.0])
            t_len = np.linalg.norm(mid_s - mid_h)
            if t_len > 0.05:
                torso_lengths.append(t_len)

        if sr and er:
            h_len = np.linalg.norm(np.array(sr[:2]) - np.array(er[:2]))
            if h_len > 0.04:
                humerus_lengths.append(h_len)

    avg_torso_norm = float(np.median(torso_lengths)) if torso_lengths else 0.30

    if user_height_cm and user_height_cm > 100:
        height_m = user_height_cm / 100.0
        # Anthropometric model: Adult torso (mid-shoulder to mid-hip) ~ 0.30 x Height
        expected_torso_m = 0.30 * height_m
        scale_m_per_coord = expected_torso_m / max(0.08, avg_torso_norm)
        confidence_desc = f"MODERATE-HIGH (Calibrated to {int(user_height_cm)} cm height)"
    else:
        # Unanchored anthropometric baseline (~0.50m torso standard)
        scale_m_per_coord = 0.50 / max(0.08, avg_torso_norm)
        confidence_desc = "MODERATE-LOW (Unanchored Anthropometry)"

    return scale_m_per_coord, confidence_desc


def calculate_rep_velocities(
    raw_reps: List[Dict[str, Any]],
    scale_m_per_coord: float
) -> List[Dict[str, Any]]:
    """
    Calculates mean concentric velocity (m/s) and peak concentric velocity (m/s).
    """
    vbt_reps = []
    for rep in raw_reps:
        conc_duration = rep.get("concentric_tempo", 0.0)
        travel_coords = rep.get("concentric_travel", 0.0)
        dist_m = travel_coords * scale_m_per_coord

        if conc_duration > 0:
            mean_v = dist_m / conc_duration
        else:
            mean_v = 0.0

        peak_v = mean_v * 1.40

        vbt_reps.append({
            "mean_velocity_mps": float(round(mean_v, 2)),
            "peak_velocity_mps": float(round(peak_v, 2)),
            "displacement_m": float(round(dist_m, 3))
        })

    return vbt_reps


def estimate_rpe_and_rir(
    vbt_reps: List[Dict[str, Any]],
    rom_percentages: List[float] = None
) -> Tuple[float, int, float, bool, str, str]:
    """
    Evaluates set-level VBT velocity loss and estimated effort.
    Returns:
        (estimated_rpe, estimated_rir, velocity_loss_pct, vl_available, vl_reason_code, vl_explanation)
    """
    if not vbt_reps:
        return 0.0, 0, 0.0, False, "NO_REPS", "No repetitions detected in clip."

    mean_velocities = [r["mean_velocity_mps"] for r in vbt_reps if r["mean_velocity_mps"] > 0]
    if not mean_velocities:
        return 0.0, 0, 0.0, False, "ZERO_VELOCITY", "No valid concentric velocities computed."

    # 1. Evaluate Set-Level ROM Gating & Comparability
    vl_available = True
    vl_reason_code = "VALID"
    vl_explanation = "Set velocity loss computed from fastest rep to final rep across comparable ROM reps."

    if rom_percentages and len(rom_percentages) > 1:
        # Check if final rep is partial
        if rom_percentages[-1] < 70.0:
            vl_available = False
            vl_reason_code = "FINAL_REP_PARTIAL"
            vl_explanation = "Set velocity loss unavailable: Final repetition did not satisfy full ROM comparability criteria."
        else:
            # Check overall ROM standard deviation
            rom_std = float(np.std(rom_percentages))
            if rom_std > 15.0:
                vl_available = False
                vl_reason_code = "ROM_INCONSISTENT"
                vl_explanation = "Set velocity loss unavailable: Repetition ROM varied significantly (comparing partial reps to full reps is invalid)."

    fastest_v = max(mean_velocities)
    final_v = mean_velocities[-1]

    if vl_available and fastest_v > 0 and final_v < fastest_v:
        vl_pct = max(0.0, ((fastest_v - final_v) / fastest_v) * 100.0)
    else:
        vl_pct = 0.0

    # RPE & RIR estimation rules
    if final_v <= 0.08 or (vl_available and vl_pct >= 40.0):
        rpe = 9.5
        rir = 0
    elif final_v <= 0.11 or (vl_available and vl_pct >= 30.0):
        rpe = 9.0
        rir = 0
    elif final_v <= 0.13 or (vl_available and vl_pct >= 22.0):
        rpe = 8.5
        rir = 1
    elif final_v <= 0.16 or (vl_available and vl_pct >= 15.0):
        rpe = 7.5
        rir = 2
    elif final_v <= 0.20 or (vl_available and vl_pct >= 10.0):
        rpe = 7.0
        rir = 3
    else:
        rpe = 6.5
        rir = 4

    return float(round(rpe, 1)), rir, float(round(vl_pct, 1)), vl_available, vl_reason_code, vl_explanation
