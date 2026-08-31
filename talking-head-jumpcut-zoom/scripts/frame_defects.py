#!/usr/bin/env python3
"""
Frame Defect Analysis and Quality Metrics (from sceneflow / MediaPipe / OpenCV specifications).
Formulas for detecting unusable cut boundaries:
1. EAR (Eye Aspect Ratio): Blink detection.
2. MAR (Mouth Aspect Ratio): Unnatural mouth openness / mid-syllable cuts.
3. Laplacian Variance: Motion blur detection.
4. Farneback Optical Flow Velocity: Head motion instability.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

# Constants for thresholding
EAR_BLINK_THRESHOLD = 0.20
EAR_OPEN_THRESHOLD = 0.25
MAR_OPEN_THRESHOLD = 0.45
LAPLACIAN_BLUR_THRESHOLD = 60.0
FLOW_MOTION_THRESHOLD_PX = 2.0


def calculate_ear(eye_landmarks: Sequence[Sequence[float]]) -> float:
    """
    Calculate Eye Aspect Ratio (EAR) from 6 2D points [p1, p2, p3, p4, p5, p6].
    p1: outer corner, p4: inner corner
    p2, p3: upper eyelid, p6, p5: lower eyelid
    EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
    """
    if len(eye_landmarks) != 6:
        raise ValueError("EAR requires exactly 6 landmarks (p1..p6)")

    def dist(p_a: Sequence[float], p_b: Sequence[float]) -> float:
        return math.hypot(p_a[0] - p_b[0], p_a[1] - p_b[1])

    p1, p2, p3, p4, p5, p6 = eye_landmarks
    v1 = dist(p2, p6)
    v2 = dist(p3, p5)
    h = dist(p1, p4)
    if h <= 1e-6:
        return 0.0
    return (v1 + v2) / (2.0 * h)


def calculate_mar(mouth_landmarks: Sequence[Sequence[float]]) -> float:
    """
    Calculate Mouth Aspect Ratio (MAR) from 6 or 8 mouth landmarks.
    Standard 6-point: [m1, m2, m3, m4, m5, m6]
    m1: left corner, m4: right corner
    m2, m3: upper lip, m6, m5: lower lip
    MAR = (||m2 - m6|| + ||m3 - m5||) / (2 * ||m1 - m4||)
    """
    if len(mouth_landmarks) < 6:
        raise ValueError("MAR requires at least 6 mouth landmarks")

    def dist(p_a: Sequence[float], p_b: Sequence[float]) -> float:
        return math.hypot(p_a[0] - p_b[0], p_a[1] - p_b[1])

    m1 = mouth_landmarks[0]
    m4 = mouth_landmarks[3]
    m2 = mouth_landmarks[1]
    m3 = mouth_landmarks[2]
    m5 = mouth_landmarks[4]
    m6 = mouth_landmarks[5]

    v1 = dist(m2, m6)
    v2 = dist(m3, m5)
    h = dist(m1, m4)
    if h <= 1e-6:
        return 0.0
    return (v1 + v2) / (2.0 * h)


def evaluate_frame_quality(
    observation: dict[str, Any],
    *,
    ear_threshold: float = EAR_BLINK_THRESHOLD,
    mar_threshold: float = MAR_OPEN_THRESHOLD,
    blur_threshold: float = LAPLACIAN_BLUR_THRESHOLD,
    flow_threshold: float = FLOW_MOTION_THRESHOLD_PX,
) -> tuple[bool, list[str]]:
    """
    Evaluate if a frame is clean and safe for a jumpcut/reframe boundary.
    Returns (is_clean, reasons_if_rejected).
    """
    reasons: list[str] = []

    # 1. EAR Check (Blink / Half-closed eyes)
    left_ear = observation.get("left_ear")
    right_ear = observation.get("right_ear")
    ear = observation.get("ear")
    if ear is None and left_ear is not None and right_ear is not None:
        ear = (float(left_ear) + float(right_ear)) / 2.0

    if ear is not None and float(ear) < ear_threshold:
        reasons.append("blink_ear")
    elif observation.get("blink", False) or observation.get("eyes_closed", False):
        reasons.append("blink_flag")

    # 2. MAR Check (Mouth Open / Mid-speech distortion)
    mar = observation.get("mar")
    if mar is not None and float(mar) > mar_threshold:
        reasons.append("mouth_open_mar")

    # 3. Laplacian Blur Check
    laplacian_var = observation.get("laplacian_var")
    if laplacian_var is not None and float(laplacian_var) < blur_threshold:
        reasons.append("motion_blur")
    elif observation.get("blur", False):
        reasons.append("blur_flag")

    # 4. Farneback Optical Flow Motion Velocity
    flow_speed = observation.get("flow_speed_px") or observation.get("motion_speed_px")
    if flow_speed is not None and float(flow_speed) > flow_threshold:
        reasons.append("high_motion_velocity")

    # 5. Pose & Gesture hard blocks
    if observation.get("pose_unsafe", False) or observation.get("strong_head_turn", False):
        reasons.append("pose_unsafe")
    if observation.get("hard_block", False) or observation.get("gesture_hard_block", False):
        reasons.append("gesture_hard_block")

    is_clean = len(reasons) == 0
    return is_clean, reasons
