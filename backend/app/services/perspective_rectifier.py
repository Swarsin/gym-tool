"""
Perspective Rectifier — Estimates camera pitch and roll tilt angles from torso & pelvis
reference vectors, and applies 2D/3D homography matrix rectification to normalize
landmark coordinates (x, y) into an orthogonal reference frame (x', y').

This eliminates geometric foreshortening and angle hallucination caused by arbitrary
tripod heights (low-floor phone shots, high-angle camera clips, tilted phones).
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple


def estimate_camera_tilt(frame_data: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    Estimate camera pitch (tilt up/down) and roll (tilt side-to-side) in degrees.

    - Roll: Angle of the lateral shoulder vector (shoulder_l -> shoulder_r) relative to horizontal.
    - Pitch: Angle of the vertical spine vector (mid_hip -> mid_shoulder) relative to vertical.

    Returns:
        Tuple[float, float]: (camera_pitch_deg, camera_roll_deg)
    """
    pitches = []
    rolls = []

    for fd in frame_data:
        lm = fd.get('landmarks', {})
        if not lm:
            continue

        sr = np.array(lm.get('shoulder_r', [0, 0, 0]))[:2]
        sl = np.array(lm.get('shoulder_l', [0, 0, 0]))[:2]
        hr = np.array(lm.get('hip_r', [0, 0, 0]))[:2]
        hl = np.array(lm.get('hip_l', [0, 0, 0]))[:2]

        # 1. Roll angle: lateral vector (sl - sr) if in front/back view
        lat_vec = sl - sr
        if abs(lat_vec[0]) > 0.20:
            roll_rad = np.arctan2(lat_vec[1], lat_vec[0])
            rolls.append(np.degrees(roll_rad))

        # 2. Pitch angle: spine vector from mid-hip to mid-shoulder
        mid_shoulder = (sr + sl) / 2.0
        mid_hip = (hr + hl) / 2.0
        spine_vec = mid_shoulder - mid_hip  # Points UP the torso
        norm_spine = np.linalg.norm(spine_vec)
        if norm_spine > 0.10:
            # MediaPipe Y points DOWN, so straight up is [0, -1]
            pitch_rad = np.arctan2(spine_vec[0], -spine_vec[1])
            pitches.append(np.degrees(pitch_rad))

    avg_pitch = float(np.median(pitches)) if pitches else 0.0
    avg_roll = float(np.median(rolls)) if rolls else 0.0

    # Bound angles within realistic tripod tilt limits
    avg_pitch = float(np.clip(avg_pitch, -30.0, 30.0))
    avg_roll = float(np.clip(avg_roll, -20.0, 20.0))

    return avg_pitch, avg_roll


def build_rectification_matrix(pitch_deg: float, roll_deg: float) -> np.ndarray:
    """
    Construct a 3x3 Homography Matrix H to rotate and rectify normalized coordinates [0, 1].

    Args:
        pitch_deg: Camera pitch offset in degrees.
        roll_deg: Camera roll offset in degrees.

    Returns:
        np.ndarray: 3x3 Homography matrix H.
    """
    cx, cy = 0.5, 0.5
    angle_deg = -roll_deg

    # 2D Rotation Matrix around (0.5, 0.5)
    rot_2d = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)

    # Convert 2x3 Affine Matrix to 3x3 Homography Matrix
    H = np.eye(3, dtype=np.float64)
    H[:2, :] = rot_2d

    # Apply vertical scale compensation for pitch foreshortening if pitch is non-zero
    if abs(pitch_deg) > 5.0:
        scale_y = 1.0 / max(0.5, float(np.cos(np.radians(pitch_deg))))
        S = np.array([
            [1.0, 0.0, 0.0],
            [0.0, scale_y, cy * (1.0 - scale_y)],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)
        H = S @ H

    return H


def rectify_landmarks(frame_data: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Rectifies frame_data landmark coordinates to eliminate camera angle distortion.

    Returns:
        Tuple[List[Dict[str, Any]], Dict[str, Any]]: (rectified_frame_data, metadata)
    """
    if not frame_data:
        return frame_data, {"camera_pitch_deg": 0.0, "camera_roll_deg": 0.0, "rectified": False}

    pitch_deg, roll_deg = estimate_camera_tilt(frame_data)
    
    # Only apply rectification if significant tilt is detected (> 2.5 degrees)
    if abs(pitch_deg) <= 2.5 and abs(roll_deg) <= 2.5:
        return frame_data, {
            "camera_pitch_deg": round(pitch_deg, 1),
            "camera_roll_deg": round(roll_deg, 1),
            "rectified": False
        }

    H = build_rectification_matrix(pitch_deg, roll_deg)

    rectified_frame_data = []
    for fd in frame_data:
        lm = fd.get('landmarks', {})
        if not lm:
            rectified_frame_data.append(fd)
            continue

        rectified_lm = {}
        for joint_name, coords in lm.items():
            x, y = coords[0], coords[1]
            pt = np.array([x, y, 1.0], dtype=np.float64)
            pt_transformed = H @ pt
            
            if pt_transformed[2] != 0:
                rx = pt_transformed[0] / pt_transformed[2]
                ry = pt_transformed[1] / pt_transformed[2]
            else:
                rx, ry = x, y

            rectified_lm[joint_name] = [float(rx), float(ry)] + coords[2:]

        rectified_frame_data.append({
            "frame_index": fd.get("frame_index", 0),
            "landmarks": rectified_lm
        })

    return rectified_frame_data, {
        "camera_pitch_deg": round(pitch_deg, 1),
        "camera_roll_deg": round(roll_deg, 1),
        "rectified": True
    }
