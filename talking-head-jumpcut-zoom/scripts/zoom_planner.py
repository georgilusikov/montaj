#!/usr/bin/env python3
"""
Montaj v1.7 Lite Semantic Zoom Planner with:
1. Two-phase architecture (Dense timeline input).
2. WHY (semantic importance + direction + ratchet escalation).
3. Eye-line anchor formula for slow_push: Delta_Y = (Y_eyes - Y_center) * (1 - 1/scale).
4. Tripod Lock: Segment-wide median crop lock (no per-frame drift).
5. Segment-wide headroom: preserve >=5% air above the highest hair point.
6. Strict defect filtering (EAR blink, MAR mouth distortion, Laplacian blur, Farneback velocity).
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

STATE_TARGET = {"CONTEXT": 0.30, "ARGUMENT": 0.35, "EMPHASIS": 0.41}
STATE_CAP = {"CONTEXT": 1.00, "ARGUMENT": 1.08, "EMPHASIS": 1.12}
ABSOLUTE_ZOOM_CAP = 1.13
STYLE_CAP = {"calm": 1.10, "moderate": 1.12, "dynamic": 1.13}
MIN_STEP = {"calm": 0.04, "moderate": 0.035, "dynamic": 0.04}
MIN_DWELL_MS = {"calm": 2000, "moderate": 1500, "dynamic": 1200}

PREFERRED_CHANGE_MS = {"calm": 3000, "moderate": 2500, "dynamic": 2200}
CADENCE_BONUS_MAX = 0.10
CADENCE_TOLERANCE_MS = 900
VISUAL_REFRESH_TARGET_MS = {"calm": 4000, "moderate": 3500, "dynamic": 3000}
VISUAL_REFRESH_MAX_MS = {"calm": 5500, "moderate": 5000, "dynamic": 4500}
CADENCE_REQUEST_HALF_WINDOW_MS = 750

# Ratchet escalation stays restrained. RATCHET_3 is the only path above normal
# EMPHASIS and is still bounded by the global artistic 1.13x cap.
RATCHET_LEVELS = {
    "RATCHET_1": 1.08,
    "RATCHET_2": 1.12,
    "RATCHET_3": 1.13,
}

SOFT_BUILD_SCALE = {"calm": 1.03, "moderate": 1.05, "dynamic": 1.06}
SOFT_BUILD_PUSH_MS = {"calm": 2800, "moderate": 2400, "dynamic": 2000}

ZOOM_DURATION_BANDS_MS = {
    "micro_punch": (500, 1200, 800),
    "beat": (1200, 2000, 1600),
    "argument_hold": (2000, 2500, 2200),
}
CONTINUATION_GRACE_MS = 500
STRONG_PEAK_MIN_DWELL_MS = 800
STRONG_PEAK_IMPORTANCE = 0.92
EMPHASIS_IMPORTANCE = 0.85
FACE_EDGE_MARGIN = 0.035
MIN_HEADROOM_RATIO = 0.05
HEADROOM_TOLERANCE = 0.002
STATE_LEVEL = {"CONTEXT": 0, "ARGUMENT": 1, "EMPHASIS": 2}
SEMANTIC_DIRECTIONS = {"BUILD", "PEAK", "RELEASE", "NEUTRAL", "RATCHET_1", "RATCHET_2", "RATCHET_3"}
MOTION_HINTS = {"AUTO", "STEP", "SLOW_PUSH"}


def _even(value: float, minimum: int = 2) -> int:
    n = max(minimum, int(round(value)))
    return n if n % 2 == 0 else n - 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _state_for_importance(value: float) -> str:
    value = _clamp(float(value), 0.0, 1.0)
    if value >= EMPHASIS_IMPORTANCE:
        return "EMPHASIS"
    if value >= 0.40:
        return "ARGUMENT"
    return "CONTEXT"


def _directed_state(base_desired: str, current_state: str, raw_direction: Any) -> tuple[str, str]:
    if raw_direction is None or not str(raw_direction).strip():
        return base_desired, "auto"

    direction = str(raw_direction).strip().upper()
    if direction not in SEMANTIC_DIRECTIONS:
        return base_desired, "auto"
    if direction == "NEUTRAL":
        return current_state, "neutral"
    if direction == "RELEASE":
        return "CONTEXT", "release"
    if direction == "PEAK":
        return base_desired, "peak"
    if direction == "RATCHET_1":
        return "ARGUMENT", "ratchet_1"
    if direction == "RATCHET_2":
        return "ARGUMENT", "ratchet_2"
    if direction == "RATCHET_3":
        return "EMPHASIS", "ratchet_3"

    # BUILD rises at most to ARGUMENT
    if STATE_LEVEL[current_state] >= STATE_LEVEL["ARGUMENT"]:
        return current_state, "build"
    if STATE_LEVEL[base_desired] >= STATE_LEVEL["ARGUMENT"]:
        return "ARGUMENT", "build"
    return current_state, "build"


def _zoom_duration(event: dict[str, Any], start_ms: int) -> tuple[str, int]:
    explicit = str(event.get("zoom_duration_type") or "").strip().lower()
    raw_ms = max(0, int(event.get("end_ms", start_ms)) - start_ms)
    if explicit in ZOOM_DURATION_BANDS_MS:
        kind = explicit
    elif raw_ms and raw_ms < 1500:
        kind = "micro_punch"
    elif raw_ms and raw_ms < 2500:
        kind = "beat"
    elif raw_ms:
        kind = "argument_hold"
    else:
        kind = "beat"
    lo, hi, default = ZOOM_DURATION_BANDS_MS[kind]
    duration = default if raw_ms <= 0 else int(_clamp(raw_ms, lo, hi))
    return kind, duration


def _samples(observations: list[dict[str, Any]], center_ms: int, window_ms: int) -> list[dict[str, Any]]:
    half = max(1, window_ms // 2)
    rows = [o for o in observations if center_ms - half <= int(o["t_ms"]) <= center_ms + half]
    if rows:
        return rows
    if not observations:
        raise ValueError("analysis.observations is empty")
    return [min(observations, key=lambda o: abs(int(o["t_ms"]) - center_ms))]


def _segment_samples(
    observations: list[dict[str, Any]],
    start_ms: int,
    end_ms: int,
    fallback_window_ms: int,
) -> list[dict[str, Any]]:
    """Samples the whole anticipated framing episode so headroom is segment-wide."""
    lo = min(int(start_ms), int(end_ms))
    hi = max(int(start_ms), int(end_ms))
    rows = [o for o in observations if lo <= int(o["t_ms"]) <= hi]
    return rows or _samples(observations, int(start_ms), fallback_window_ms)


def _get_global_anchor(observations: list[dict[str, Any]]) -> tuple[float, float, float]:
    """
    Compute robust global optical center (cx, cy, eye_y) across entire video.
    Filters out spurious false-positive detections (e.g. hands/watch/lapels in lower half).
    """
    if not observations:
        return 0.50, 0.34, 0.29
    valid = [
        o for o in observations
        if 0.15 <= float(o.get("face_cy", 0.35)) <= 0.55 and 0.30 <= float(o.get("face_cx", 0.50)) <= 0.70
    ]
    pool = valid if valid else observations
    cx = median(float(o.get("face_cx", 0.50)) for o in pool)
    cy = median(float(o.get("face_cy", 0.34)) for o in pool)
    eye_y = median(float(o.get("eye_line_y", cy - 0.05)) for o in pool)
    return cx, cy, eye_y


def _crop_for_scale_with_anchor(
    rows: list[dict[str, Any]],
    width: int,
    height: int,
    scale: float,
    global_anchor: tuple[float, float, float] | None = None,
) -> tuple[int, int, int, int]:
    """
    Calculate crop using Tripod Lock + eye anchor, then restore the older segment-wide
    headroom invariant: use the highest hair point across the whole shot and shift the
    crop upward as needed to keep >=5% of the output crop above it.
    """
    if scale <= 1.000001:
        return 0, 0, width, height

    crop_w = _even(width / scale)
    crop_h = _even(height / scale)

    if global_anchor is not None:
        cx, cy, y_eyes_norm = global_anchor
    else:
        cx = median(float(o.get("face_cx", 0.5)) for o in rows)
        cy = median(float(o.get("face_cy", 0.34)) for o in rows)
        y_eyes_norm = median(float(o.get("eye_line_y", cy - 0.05)) for o in rows)

    y_eyes_px = y_eyes_norm * height
    y_center_px = 0.50 * height

    # Eye Anchor Holding formula: Delta_Y = (Y_eyes - Y_center) * (1 - 1/scale)
    delta_y_anchor = (y_eyes_px - y_center_px) * (1.0 - 1.0 / scale)
    base_y = (height - crop_h) / 2.0 + delta_y_anchor

    # Restored v1.x segment-wide headroom formula:
    # hair_top_segment = min(hair_top[t])
    # Y_crop = min(Y_default, hair_top_segment - 0.05 * crop_h)
    hair_tops = [float(o["hair_top"]) for o in rows if o.get("hair_top") is not None]
    if hair_tops:
        hair_top_segment_px = min(hair_tops) * height
        required_headroom_px = MIN_HEADROOM_RATIO * crop_h
        base_y = min(base_y, hair_top_segment_px - required_headroom_px)

    x = _even(_clamp(cx * width - crop_w / 2, 0, width - crop_w), 0)
    y = _even(_clamp(base_y, 0, height - crop_h), 0)
    return x, y, crop_w, crop_h


def _face_box_px(row: dict[str, Any], width: int, height: int) -> tuple[float, float, float, float]:
    bbox = row.get("face_bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        left, top, right, bottom = (float(v) for v in bbox)
        return left * width, top * height, right * width, bottom * height
    cx = float(row.get("face_cx", 0.5)) * width
    cy = float(row.get("face_cy", 0.34)) * height
    face_h = max(1.0, float(row.get("face_ratio", 0.0)) * height)
    face_w = 0.78 * face_h
    return cx - face_w / 2, cy - face_h / 2, cx + face_w / 2, cy + face_h / 2


def _min_headroom_ratio(
    rows: list[dict[str, Any]],
    crop: tuple[int, int, int, int] | list[int],
    height: int,
) -> float | None:
    _, y, _, crop_h = (int(v) for v in crop)
    values = [
        (float(row["hair_top"]) * height - y) / crop_h
        for row in rows
        if row.get("hair_top") is not None
    ]
    return min(values) if values else None


def _crop_safe(
    rows: list[dict[str, Any]],
    crop: tuple[int, int, int, int],
    width: int,
    height: int,
    scale: float,
) -> tuple[bool, list[str]]:
    x, y, crop_w, crop_h = crop
    reasons: list[str] = []
    if x < 0 or y < 0 or x + crop_w > width or y + crop_h > height:
        reasons.append("crop_bounds")

    margin_x = FACE_EDGE_MARGIN * crop_w
    margin_y = FACE_EDGE_MARGIN * crop_h
    for row in rows:
        if bool(row.get("hard_block", False)) or bool(row.get("gesture_hard_block", False)):
            reasons.append("hard_gesture_or_prop")
            break
        if float(row.get("caption_overlap", 0.0)) > 0.0:
            reasons.append("caption_overlap")
            break
        if float(row.get("face_ratio", 0.0)) * scale > 0.46:
            reasons.append("face_too_large")
            break
        face_left, face_top, face_right, face_bottom = _face_box_px(row, width, height)
        if (
            face_left < x + margin_x
            or face_right > x + crop_w - margin_x
            or face_top < y + margin_y
            or face_bottom > y + crop_h - margin_y
        ):
            reasons.append("face_travel")
            break
        hair_top = row.get("hair_top")
        if hair_top is not None:
            hair_out = (float(hair_top) * height - y) / crop_h
            if hair_out + HEADROOM_TOLERANCE < MIN_HEADROOM_RATIO:
                reasons.append("headroom")
                break
    return not reasons, reasons


UPPER_STATE_MIN_STEP = 0.025


def _candidate_states(
    rows: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    intensity: str,
    quality_cap: float,
    absolute_cap: float,
    state_caps: dict[str, float],
    global_anchor: tuple[float, float, float] | None = None,
) -> list[dict[str, Any]]:
    face_base = median(max(1e-6, float(o.get("face_ratio", 0.0))) for o in rows)
    candidates: list[dict[str, Any]] = []
    for state in ("CONTEXT", "ARGUMENT", "EMPHASIS"):
        desired_scale = max(1.0, STATE_TARGET[state] / face_base)
        effective_cap = min(quality_cap, STYLE_CAP[intensity], absolute_cap, float(state_caps[state]))
        scale = min(desired_scale, effective_cap)
        crop = _crop_for_scale_with_anchor(rows, width, height, scale, global_anchor=global_anchor)
        safe, _ = _crop_safe(rows, crop, width, height, scale)
        if safe:
            headroom_ratio = _min_headroom_ratio(rows, crop, height)
            candidates.append(
                {
                    "state": state,
                    "scale": round(scale, 4),
                    "crop": list(crop),
                    "face_ratio": round(face_base * scale, 4),
                    "desired_scale": round(desired_scale, 4),
                    "effective_cap": round(effective_cap, 4),
                    "limited": scale + 1e-6 < desired_scale,
                    "headroom_ratio": round(headroom_ratio, 4) if headroom_ratio is not None else None,
                }
            )

    distinct: list[dict[str, Any]] = []
    for candidate in candidates:
        if not distinct:
            distinct.append(candidate)
            continue
        delta = abs(candidate["scale"] / distinct[-1]["scale"] - 1.0)
        upper_pair = candidate["state"] == "EMPHASIS" and distinct[-1]["state"] == "ARGUMENT"
        threshold = UPPER_STATE_MIN_STEP if upper_pair else MIN_STEP[intensity]
        if delta >= threshold:
            distinct.append(candidate)
    return distinct


def _choose_state(states: list[dict[str, Any]], desired: str) -> dict[str, Any] | None:
    allowed = [s for s in states if STATE_LEVEL[s["state"]] <= STATE_LEVEL[desired]]
    if allowed:
        return max(allowed, key=lambda s: STATE_LEVEL[s["state"]])
    return states[0] if states else None


def _soft_build_state(
    selected: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    intensity: str,
    global_anchor: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    if selected["state"] != "ARGUMENT":
        return selected
    scale = min(float(selected["scale"]), SOFT_BUILD_SCALE[intensity])
    if scale <= 1.000001:
        return selected
    crop = _crop_for_scale_with_anchor(rows, width, height, scale, global_anchor=global_anchor)
    safe, _ = _crop_safe(rows, crop, width, height, scale)
    if not safe:
        return selected
    result = dict(selected)
    result["scale"] = round(scale, 4)
    result["crop"] = list(crop)
    result["face_ratio"] = round(median(float(o.get("face_ratio", 0.0)) for o in rows) * scale, 4)
    headroom_ratio = _min_headroom_ratio(rows, crop, height)
    result["headroom_ratio"] = round(headroom_ratio, 4) if headroom_ratio is not None else None
    result["soft_build"] = True
    return result


def _ratchet_state(
    direction: str,
    selected: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    intensity: str,
    quality_cap: float,
    absolute_cap: float,
    global_anchor: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    """Apply restrained ratchet escalation: 1.08 -> 1.12 -> max 1.13."""
    target_scale = RATCHET_LEVELS.get(direction.upper(), float(selected["scale"]))
    effective_scale = min(target_scale, quality_cap, STYLE_CAP[intensity], absolute_cap)
    crop = _crop_for_scale_with_anchor(rows, width, height, effective_scale, global_anchor=global_anchor)
    safe, _ = _crop_safe(rows, crop, width, height, effective_scale)
    if not safe:
        return selected
    result = dict(selected)
    result["scale"] = round(effective_scale, 4)
    result["crop"] = list(crop)
    result["face_ratio"] = round(median(float(o.get("face_ratio", 0.0)) for o in rows) * effective_scale, 4)
    headroom_ratio = _min_headroom_ratio(rows, crop, height)
    result["headroom_ratio"] = round(headroom_ratio, 4) if headroom_ratio is not None else None
    result["ratchet"] = direction.lower()
    return result


def _choose_boundary(
    event_ms: int,
    candidates: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    selected_state: dict[str, Any],
    *,
    width: int,
    height: int,
    window_ms: int,
    min_ms: int | None = None,
    last_change_ms: int | None = None,
    preferred_change_ms: int | None = None,
) -> dict[str, Any] | None:
    ranked: list[tuple[float, int, str, dict[str, Any]]] = []
    for raw in candidates:
        # Defect rejection: EAR, MAR, blur, optical flow velocity
        if any(raw.get(k) for k in ("blink", "blur", "hard_block", "eyes_closed", "long_eye_closure", "pose_unsafe", "strong_head_turn")):
            continue
        ear = raw.get("ear")
        if ear is not None and float(ear) < 0.20:
            continue
        mar = raw.get("mar")
        if mar is not None and float(mar) > 0.45:
            continue
        laplacian_var = raw.get("laplacian_var")
        if laplacian_var is not None and float(laplacian_var) < 60.0:
            continue
        flow_speed = raw.get("flow_speed_px") or raw.get("motion_speed_px")
        if flow_speed is not None and float(flow_speed) > 2.0:
            continue

        ms = int(raw["ms"])
        if min_ms is not None and ms < min_ms:
            continue
        rows = _samples(observations, ms, window_ms)
        if any(bool(row.get(k, False)) for row in rows for k in ("long_eye_closure", "pose_unsafe", "strong_head_turn")):
            continue
        crop = tuple(int(v) for v in selected_state["crop"])
        safe, _ = _crop_safe(rows, crop, width, height, float(selected_state["scale"]))
        if not safe:
            continue

        proximity = max(0.0, 1.0 - abs(ms - event_ms) / 1500.0)
        score = proximity
        score += 0.25 if raw.get("word_boundary") else 0.0
        score += 0.20 if raw.get("pause") else 0.0
        score += 0.15 if raw.get("head_return") else 0.0
        cadence_bonus = 0.0
        if last_change_ms is not None and preferred_change_ms is not None and ms > last_change_ms:
            cadence_error = abs((ms - last_change_ms) - preferred_change_ms)
            cadence_fit = max(0.0, 1.0 - cadence_error / CADENCE_TOLERANCE_MS)
            cadence_bonus = CADENCE_BONUS_MAX * cadence_fit
            score += cadence_bonus
        enriched = dict(raw)
        enriched["cadence_bonus"] = round(cadence_bonus, 6)
        ranked.append((round(score, 6), ms, str(raw.get("id", "")), enriched))

    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    chosen = dict(ranked[0][3])
    chosen["score"] = ranked[0][0]
    return chosen


def _context_state(states: list[dict[str, Any]], width: int, height: int) -> dict[str, Any]:
    for state in states:
        if state["state"] == "CONTEXT":
            return state
    return {"state": "CONTEXT", "scale": 1.0, "crop": [0, 0, width, height]}


def _return_event(pending: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_ms": int(pending["at_ms"]),
        "end_ms": int(pending["at_ms"]),
        "state": "CONTEXT",
        "motion": "step",
        "crop_start": list(pending["crop_start"]),
        "crop_end": list(pending["crop_end"]),
        "scale": float(pending["scale"]),
        "why": "auto_return_context",
        "parent_event_id": pending.get("parent_event_id"),
    }


def _cadence_requests(
    *,
    duration_ms: int,
    content_cuts_ms: list[int],
    decisions: list[dict[str, Any]],
    returns: list[dict[str, Any]],
    intensity: str,
) -> tuple[list[int], list[dict[str, Any]]]:
    if duration_ms <= 0:
        return [], []

    changes = {0, duration_ms}
    changes.update(max(0, min(duration_ms, int(t))) for t in content_cuts_ms)
    for item in decisions:
        if item.get("status") == "PLANNED" and item.get("crop_start") != item.get("crop_end"):
            changes.add(max(0, min(duration_ms, int(item["start_ms"]))))
    for item in returns:
        if item.get("crop_start") != item.get("crop_end"):
            changes.add(max(0, min(duration_ms, int(item["start_ms"]))))

    known = sorted(changes)
    target = VISUAL_REFRESH_TARGET_MS[intensity]
    maximum = VISUAL_REFRESH_MAX_MS[intensity]
    requests: list[dict[str, Any]] = []
    for left, right in zip(known, known[1:]):
        cursor = left
        while right - cursor > maximum:
            at_ms = min(cursor + target, right - 1000)
            if at_ms <= cursor:
                break
            requests.append(
                {
                    "at_ms": at_ms,
                    "window_start_ms": max(cursor + 2000, at_ms - CADENCE_REQUEST_HALF_WINDOW_MS),
                    "window_end_ms": min(right - 500, at_ms + CADENCE_REQUEST_HALF_WINDOW_MS),
                    "preferred_action": "jumpcut_same_scale",
                    "fallback_action": "hold_if_no_safe_cut",
                    "why": "visual_refresh_gap",
                    "semantic_trigger": False,
                    "gap_start_ms": cursor,
                    "gap_end_ms": right,
                }
            )
            cursor = at_ms
    return known, requests


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    source = dict(payload.get("source") or {})
    width = int(source["width"])
    height = int(source["height"])
    quality_cap = float(source.get("quality_cap", 1.16))
    if quality_cap < 1.0:
        raise ValueError("quality_cap must be >= 1.00")

    config = dict(payload.get("config") or {})
    intensity = str(config.get("intensity", "moderate"))
    if intensity not in STYLE_CAP:
        raise ValueError(f"unknown intensity: {intensity}")
    window_ms = int(config.get("window_ms", 1200))
    absolute_cap = min(float(config.get("absolute_zoom_cap", ABSOLUTE_ZOOM_CAP)), ABSOLUTE_ZOOM_CAP)
    min_dwell_ms = max(0, int(config.get("min_dwell_ms", MIN_DWELL_MS[intensity])))
    preferred_change_ms = max(0, int(config.get("preferred_change_ms", PREFERRED_CHANGE_MS[intensity])))
    peak_min_dwell_ms = max(0, int(config.get("peak_min_dwell_ms", STRONG_PEAK_MIN_DWELL_MS)))

    state_caps = dict(STATE_CAP)
    for state, value in dict(config.get("state_caps") or {}).items():
        state = str(state).upper()
        if state in state_caps:
            state_caps[state] = min(float(value), ABSOLUTE_ZOOM_CAP)

    observations = sorted(list(payload.get("observations") or []), key=lambda o: int(o["t_ms"]))
    events = sorted(list(payload.get("semantic_events") or []), key=lambda e: (int(e["t_ms"]), str(e.get("id", ""))))
    content_cuts_ms = sorted(int(v) for v in (payload.get("content_cuts_ms") or []))

    global_anchor = _get_global_anchor(observations)

    current_state = "CONTEXT"
    current_crop = [0, 0, width, height]
    last_change_ms: int | None = None
    pending_return: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = []
    returns: list[dict[str, Any]] = []

    for index, event in enumerate(events):
        event_ms = int(event["t_ms"])
        if pending_return is not None and event_ms >= int(pending_return["at_ms"]):
            returns.append(_return_event(pending_return))
            current_state = "CONTEXT"
            current_crop = list(pending_return["crop_end"])
            last_change_ms = int(pending_return["at_ms"])
            pending_return = None

        importance = float(event.get("importance", 0.0))
        base_desired = str(event.get("type") or _state_for_importance(importance)).upper()
        if base_desired not in STATE_LEVEL:
            base_desired = _state_for_importance(importance)
        desired, direction = _directed_state(base_desired, current_state, event.get("direction"))

        # Geometry is sampled across the anticipated visible framing episode, not just
        # one boundary frame. This restores the older segment-wide headroom contract.
        if desired != "CONTEXT":
            _, preview_duration_ms = _zoom_duration(event, event_ms)
            rows = _segment_samples(observations, event_ms, event_ms + preview_duration_ms, window_ms)
        else:
            rows = _samples(observations, event_ms, window_ms)

        states = _candidate_states(
            rows,
            width=width,
            height=height,
            intensity=intensity,
            quality_cap=quality_cap,
            absolute_cap=absolute_cap,
            state_caps=state_caps,
            global_anchor=global_anchor,
        )
        selected = _choose_state(states, desired)
        if selected is None:
            decisions.append({
                "event_id": event.get("id"), "event_ms": event_ms, "status": "KEEP",
                "reason": "no_safe_state", "direction": direction,
                "base_desired_state": base_desired, "desired_state": desired,
            })
            continue

        raw_hint = str(event.get("motion_hint") or "auto").strip().upper()
        motion_hint = raw_hint if raw_hint in MOTION_HINTS else "AUTO"
        gradual_build = direction == "build" and current_state == "CONTEXT" and motion_hint == "SLOW_PUSH"
        if gradual_build:
            selected = _soft_build_state(selected, rows, width=width, height=height, intensity=intensity, global_anchor=global_anchor)
        elif direction.startswith("ratchet_"):
            selected = _ratchet_state(
                direction, selected, rows,
                width=width, height=height, intensity=intensity,
                quality_cap=quality_cap, absolute_cap=absolute_cap,
                global_anchor=global_anchor,
            )

        target_crop = list(selected["crop"])
        will_change = target_crop != current_crop
        dwell_required_ms = min_dwell_ms
        if direction == "peak" and importance >= STRONG_PEAK_IMPORTANCE:
            dwell_required_ms = min(dwell_required_ms, peak_min_dwell_ms)
        earliest_change_ms = last_change_ms + dwell_required_ms if will_change and last_change_ms is not None else None

        boundary = _choose_boundary(
            event_ms,
            list(event.get("boundary_candidates") or []),
            observations,
            selected,
            width=width,
            height=height,
            window_ms=window_ms,
            min_ms=earliest_change_ms,
            last_change_ms=last_change_ms,
            preferred_change_ms=preferred_change_ms,
        )
        if boundary is None:
            decisions.append({
                "event_id": event.get("id"), "event_ms": event_ms, "status": "KEEP",
                "reason": "no_safe_boundary", "direction": direction,
                "base_desired_state": base_desired, "desired_state": desired,
                "earliest_change_ms": earliest_change_ms,
            })
            continue

        start_ms = int(boundary["ms"])
        scale_delta = abs(float(selected["scale"]) / max(width / current_crop[2], 1e-9) - 1.0)
        if target_crop == current_crop:
            motion = "hold"
        elif motion_hint == "SLOW_PUSH":
            motion = "slow_push"
        else:
            motion = "step"

        duration_type = None
        duration_ms = None
        episode_end_ms = start_ms
        auto_return = False
        continued_by_next = False
        context = _context_state(states, width, height)
        if selected["state"] != "CONTEXT":
            duration_type, duration_ms = _zoom_duration(event, start_ms)
            episode_end_ms = start_ms + duration_ms
            next_event = events[index + 1] if index + 1 < len(events) else None
            if next_event is not None:
                next_direction = str(next_event.get("direction") or "").strip().upper()
                next_ms = int(next_event["t_ms"])
                continued_by_next = (next_direction in {"BUILD", "PEAK"} or next_direction.startswith("RATCHET_")) and next_ms <= episode_end_ms + CONTINUATION_GRACE_MS
            auto_return = not continued_by_next
            if auto_return:
                pending_return = {
                    "at_ms": episode_end_ms,
                    "crop_start": target_crop,
                    "crop_end": list(context["crop"]),
                    "scale": float(context["scale"]),
                    "parent_event_id": event.get("id"),
                }
            else:
                pending_return = None
        else:
            pending_return = None

        if motion == "slow_push" and duration_ms:
            requested_transition = int(event.get("transition_ms", SOFT_BUILD_PUSH_MS[intensity] if gradual_build else min(1800, duration_ms)))
            transition_ms = int(_clamp(requested_transition, 400, min(3000, duration_ms)))
            transition_end_ms = start_ms + transition_ms
        else:
            transition_end_ms = start_ms

        decisions.append({
            "event_id": event.get("id"),
            "event_ms": event_ms,
            "start_ms": start_ms,
            "end_ms": episode_end_ms,
            "transition_end_ms": transition_end_ms,
            "status": "PLANNED",
            "state": selected["state"],
            "base_desired_state": base_desired,
            "desired_state": desired,
            "direction": direction,
            "motion": motion,
            "motion_hint": motion_hint.lower(),
            "crop_start": list(current_crop),
            "crop_end": target_crop,
            "scale": selected["scale"],
            "state_cap": selected["effective_cap"],
            "available_states": [s["state"] for s in states],
            "why": "semantic_importance" if direction == "auto" else f"semantic_{direction}",
            "boundary_score": boundary["score"],
            "cadence_bonus": boundary.get("cadence_bonus", 0.0),
            "dwell_required_ms": dwell_required_ms,
            "zoom_duration_type": duration_type,
            "zoom_duration_ms": duration_ms,
            "episode_end_ms": episode_end_ms,
            "auto_return": auto_return,
            "continued_by_next": continued_by_next,
            "soft_build": gradual_build and bool(selected.get("soft_build", False)),
            "ratchet": selected.get("ratchet"),
            "headroom_ratio": selected.get("headroom_ratio"),
        })

        current_state = selected["state"]
        if will_change:
            last_change_ms = start_ms
        current_crop = target_crop

    if pending_return is not None:
        returns.append(_return_event(pending_return))

    event_end_ms = max((int(e.get("end_ms", e.get("t_ms", 0))) for e in events), default=0)
    observation_end_ms = max((int(o.get("t_ms", 0)) for o in observations), default=0)
    duration_ms = int(source.get("duration_ms") or max(event_end_ms, observation_end_ms))
    visual_change_times_ms, cadence_requests = _cadence_requests(
        duration_ms=duration_ms,
        content_cuts_ms=content_cuts_ms,
        decisions=decisions,
        returns=returns,
        intensity=intensity,
    )

    return {
        "version": "1.7-lite",
        "source": {"width": width, "height": height, "duration_ms": duration_ms},
        "config": {
            "intensity": intensity,
            "window_ms": window_ms,
            "quality_cap": quality_cap,
            "absolute_zoom_cap": absolute_cap,
            "state_caps": state_caps,
            "min_headroom_ratio": MIN_HEADROOM_RATIO,
            "min_dwell_ms": min_dwell_ms,
            "preferred_change_ms": preferred_change_ms,
            "visual_refresh_target_ms": VISUAL_REFRESH_TARGET_MS[intensity],
            "visual_refresh_max_ms": VISUAL_REFRESH_MAX_MS[intensity],
            "peak_min_dwell_ms": peak_min_dwell_ms,
            "emphasis_importance": EMPHASIS_IMPORTANCE,
            "strong_peak_importance": STRONG_PEAK_IMPORTANCE,
            "zoom_duration_bands_ms": ZOOM_DURATION_BANDS_MS,
            "soft_build_scale": SOFT_BUILD_SCALE[intensity],
            "soft_build_push_ms": SOFT_BUILD_PUSH_MS[intensity],
            "ratchet_levels": RATCHET_LEVELS,
        },
        "decisions": decisions,
        "returns": returns,
        "content_cuts_ms": content_cuts_ms,
        "visual_change_times_ms": visual_change_times_ms,
        "cadence_requests": cadence_requests,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Montaj v1.7 Lite semantic zoom planner")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    result = plan(payload)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
