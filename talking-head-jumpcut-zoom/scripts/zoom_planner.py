#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median
from typing import Any

STATE_TARGET = {"CONTEXT": 0.30, "ARGUMENT": 0.35, "EMPHASIS": 0.41}
# Artistic caps are intentionally independent from source resolution. 4K may make a
# crop cleaner, but it must not silently turn EMPHASIS into a 1.60x close-up.
STATE_CAP = {"CONTEXT": 1.05, "ARGUMENT": 1.12, "EMPHASIS": 1.20}
ABSOLUTE_ZOOM_CAP = 1.20
STYLE_CAP = {"calm": 1.10, "moderate": 1.16, "dynamic": 1.20}
MIN_STEP = {"calm": 0.04, "moderate": 0.06, "dynamic": 0.06}
MIN_DWELL_MS = {"calm": 2000, "moderate": 1500, "dynamic": 1200}
# Soft camera-rhythm prior, calibrated from the clean camera-layer analysis. It is
# only a boundary bonus; semantic timing remains primary.
PREFERRED_CHANGE_MS = {"calm": 3000, "moderate": 2500, "dynamic": 2200}
CADENCE_BONUS_MAX = 0.10
CADENCE_TOLERANCE_MS = 900
STRONG_PEAK_MIN_DWELL_MS = 800
STRONG_PEAK_IMPORTANCE = 0.92
EMPHASIS_IMPORTANCE = 0.85
FACE_EDGE_MARGIN = 0.035
STATE_LEVEL = {"CONTEXT": 0, "ARGUMENT": 1, "EMPHASIS": 2}
SEMANTIC_DIRECTIONS = {"BUILD", "PEAK", "RELEASE", "NEUTRAL"}


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
    """Apply a tiny dramaturgy layer without introducing a pattern engine.

    Importance/type answers how much emphasis the sentence deserves. Direction only
    controls the energy trajectory: BUILD rises at most to ARGUMENT, PEAK may use the
    normal semantic target, RELEASE returns home, and NEUTRAL explicitly holds the
    current state. This creates visual tension/release without forcing a repeating
    zoom pattern.
    """
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

    # BUILD never jumps directly to EMPHASIS and never downshifts an already-close
    # framing. It advances only when semantic importance supports ARGUMENT or higher.
    if STATE_LEVEL[current_state] >= STATE_LEVEL["ARGUMENT"]:
        return current_state, "build"
    if STATE_LEVEL[base_desired] >= STATE_LEVEL["ARGUMENT"]:
        return "ARGUMENT", "build"
    return current_state, "build"


def _samples(observations: list[dict[str, Any]], center_ms: int, window_ms: int) -> list[dict[str, Any]]:
    half = max(1, window_ms // 2)
    rows = [o for o in observations if center_ms - half <= int(o["t_ms"]) <= center_ms + half]
    if rows:
        return rows
    if not observations:
        raise ValueError("analysis.observations is empty")
    return [min(observations, key=lambda o: abs(int(o["t_ms"]) - center_ms))]


def _crop_for_scale(rows: list[dict[str, Any]], width: int, height: int, scale: float) -> tuple[int, int, int, int]:
    crop_w = _even(width / scale)
    crop_h = _even(height / scale)
    cx = median(float(o.get("face_cx", 0.5)) for o in rows)
    cy = median(float(o.get("face_cy", 0.34)) for o in rows)

    x = _even(_clamp(cx * width - crop_w / 2, 0, width - crop_w), 0)
    # Keep the face center around 34% of output height, then clamp to source bounds.
    y = _even(_clamp(cy * height - 0.34 * crop_h, 0, height - crop_h), 0)
    return x, y, crop_w, crop_h


def _face_box_px(row: dict[str, Any], width: int, height: int) -> tuple[float, float, float, float]:
    """Return a conservative face box in source pixels.

    `face_bbox`, when supplied, is normalized [left, top, right, bottom] and wins.
    Otherwise derive a conservative box from face center + face-height ratio so the
    Lite planner can still protect against subject travel without another detector.
    """
    bbox = row.get("face_bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        left, top, right, bottom = (float(v) for v in bbox)
        return left * width, top * height, right * width, bottom * height

    cx = float(row.get("face_cx", 0.5)) * width
    cy = float(row.get("face_cy", 0.34)) * height
    face_h = max(1.0, float(row.get("face_ratio", 0.0)) * height)
    face_w = 0.78 * face_h
    return cx - face_w / 2, cy - face_h / 2, cx + face_w / 2, cy + face_h / 2


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
            if hair_out < 0.04:
                reasons.append("headroom")
                break
    return not reasons, reasons


def _candidate_states(
    rows: list[dict[str, Any]],
    *,
    width: int,
    height: int,
    intensity: str,
    quality_cap: float,
    absolute_cap: float,
    state_caps: dict[str, float],
) -> list[dict[str, Any]]:
    if intensity not in STYLE_CAP:
        raise ValueError(f"unknown intensity: {intensity}")
    face_base = median(max(1e-6, float(o.get("face_ratio", 0.0))) for o in rows)
    candidates: list[dict[str, Any]] = []

    for state in ("CONTEXT", "ARGUMENT", "EMPHASIS"):
        desired_scale = max(1.0, STATE_TARGET[state] / face_base)
        effective_cap = min(
            float(quality_cap),
            STYLE_CAP[intensity],
            float(absolute_cap),
            float(state_caps[state]),
        )
        scale = min(desired_scale, effective_cap)
        crop = _crop_for_scale(rows, width, height, scale)
        safe, reasons = _crop_safe(rows, crop, width, height, scale)
        if safe:
            candidates.append(
                {
                    "state": state,
                    "scale": round(scale, 4),
                    "crop": list(crop),
                    "face_ratio": round(face_base * scale, 4),
                    "desired_scale": round(desired_scale, 4),
                    "effective_cap": round(effective_cap, 4),
                    "limited": scale + 1e-6 < desired_scale,
                }
            )

    # Keep only perceptually distinct states. If ARGUMENT is redundant but EMPHASIS
    # is distinguishable from CONTEXT, prefer the endpoint.
    distinct: list[dict[str, Any]] = []
    for candidate in candidates:
        if not distinct:
            distinct.append(candidate)
            continue
        delta = abs(candidate["scale"] / distinct[-1]["scale"] - 1.0)
        if delta >= MIN_STEP[intensity]:
            distinct.append(candidate)
        elif candidate["state"] == "EMPHASIS" and distinct[-1]["state"] == "ARGUMENT":
            if len(distinct) == 1 or abs(candidate["scale"] / distinct[-2]["scale"] - 1.0) >= MIN_STEP[intensity]:
                distinct[-1] = candidate
    return distinct


def _choose_state(states: list[dict[str, Any]], desired: str) -> dict[str, Any] | None:
    allowed = [s for s in states if STATE_LEVEL[s["state"]] <= STATE_LEVEL[desired]]
    if allowed:
        return max(allowed, key=lambda s: STATE_LEVEL[s["state"]])
    return states[0] if states else None


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
        if (
            raw.get("blink")
            or raw.get("blur")
            or raw.get("hard_block")
            or raw.get("eyes_closed")
            or raw.get("long_eye_closure")
            or raw.get("pose_unsafe")
            or raw.get("strong_head_turn")
        ):
            continue
        ms = int(raw["ms"])
        if min_ms is not None and ms < min_ms:
            continue
        rows = _samples(observations, ms, window_ms)
        if any(
            bool(row.get("long_eye_closure", False))
            or bool(row.get("pose_unsafe", False))
            or bool(row.get("strong_head_turn", False))
            for row in rows
        ):
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

    current_state = "CONTEXT"
    current_crop = [0, 0, width, height]
    last_change_ms: int | None = None
    decisions: list[dict[str, Any]] = []

    for event in events:
        event_ms = int(event["t_ms"])
        importance = float(event.get("importance", 0.0))
        base_desired = str(event.get("type") or _state_for_importance(importance)).upper()
        if base_desired not in STATE_LEVEL:
            base_desired = _state_for_importance(importance)
        desired, direction = _directed_state(base_desired, current_state, event.get("direction"))

        rows = _samples(observations, event_ms, window_ms)
        states = _candidate_states(
            rows,
            width=width,
            height=height,
            intensity=intensity,
            quality_cap=quality_cap,
            absolute_cap=absolute_cap,
            state_caps=state_caps,
        )
        selected = _choose_state(states, desired)
        if selected is None:
            decisions.append(
                {
                    "event_ms": event_ms,
                    "status": "KEEP",
                    "reason": "no_safe_state",
                    "direction": direction,
                    "base_desired_state": base_desired,
                    "desired_state": desired,
                }
            )
            continue

        target_crop = list(selected["crop"])
        will_change = target_crop != current_crop
        dwell_required_ms = min_dwell_ms
        if direction == "peak" and importance >= STRONG_PEAK_IMPORTANCE:
            dwell_required_ms = min(dwell_required_ms, peak_min_dwell_ms)
        earliest_change_ms = None
        if will_change and last_change_ms is not None:
            earliest_change_ms = last_change_ms + dwell_required_ms

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
            decisions.append(
                {
                    "event_ms": event_ms,
                    "status": "KEEP",
                    "reason": "no_safe_boundary",
                    "direction": direction,
                    "base_desired_state": base_desired,
                    "desired_state": desired,
                    "earliest_change_ms": earliest_change_ms,
                }
            )
            continue

        scale_delta = abs(selected["scale"] / max(width / current_crop[2], 1e-9) - 1.0)
        if target_crop == current_crop:
            motion = "hold"
        elif scale_delta < MIN_STEP[intensity] and importance >= EMPHASIS_IMPORTANCE:
            motion = "slow_push"
        else:
            motion = "step"

        start_ms = int(boundary["ms"])
        end_ms = max(start_ms, int(event.get("end_ms", start_ms + 1500)))
        decisions.append(
            {
                "event_ms": event_ms,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "status": "PLANNED",
                "state": selected["state"],
                "base_desired_state": base_desired,
                "desired_state": desired,
                "direction": direction,
                "motion": motion,
                "crop_start": list(current_crop),
                "crop_end": target_crop,
                "scale": selected["scale"],
                "state_cap": selected["effective_cap"],
                "available_states": [s["state"] for s in states],
                "why": "semantic_importance" if direction == "auto" else f"semantic_{direction}",
                "boundary_score": boundary["score"],
                "cadence_bonus": boundary.get("cadence_bonus", 0.0),
                "dwell_required_ms": dwell_required_ms,
            }
        )
        current_state = selected["state"]
        if will_change:
            last_change_ms = start_ms
        current_crop = target_crop

    return {
        "version": "1.7-lite",
        "source": {"width": width, "height": height},
        "config": {
            "intensity": intensity,
            "window_ms": window_ms,
            "quality_cap": quality_cap,
            "absolute_zoom_cap": absolute_cap,
            "state_caps": state_caps,
            "min_dwell_ms": min_dwell_ms,
            "preferred_change_ms": preferred_change_ms,
            "peak_min_dwell_ms": peak_min_dwell_ms,
            "emphasis_importance": EMPHASIS_IMPORTANCE,
            "strong_peak_importance": STRONG_PEAK_IMPORTANCE,
        },
        "decisions": decisions,
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