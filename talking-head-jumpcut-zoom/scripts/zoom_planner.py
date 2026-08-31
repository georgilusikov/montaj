#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

STATE_TARGET = {"CONTEXT": 0.30, "ARGUMENT": 0.35, "EMPHASIS": 0.41}
STYLE_CAP = {"calm": 1.10, "moderate": 1.16, "dynamic": 1.20}
MIN_STEP = {"calm": 0.04, "moderate": 0.06, "dynamic": 0.06}
STATE_LEVEL = {"CONTEXT": 0, "ARGUMENT": 1, "EMPHASIS": 2}


def _even(value: float, minimum: int = 2) -> int:
    n = max(minimum, int(round(value)))
    return n if n % 2 == 0 else n - 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _state_for_importance(value: float) -> str:
    value = _clamp(float(value), 0.0, 1.0)
    if value >= 0.75:
        return "EMPHASIS"
    if value >= 0.40:
        return "ARGUMENT"
    return "CONTEXT"


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
) -> list[dict[str, Any]]:
    if intensity not in STYLE_CAP:
        raise ValueError(f"unknown intensity: {intensity}")
    face_base = median(max(1e-6, float(o.get("face_ratio", 0.0))) for o in rows)
    cap = min(float(quality_cap), STYLE_CAP[intensity])
    candidates: list[dict[str, Any]] = []

    for state in ("CONTEXT", "ARGUMENT", "EMPHASIS"):
        desired_scale = max(1.0, STATE_TARGET[state] / face_base)
        scale = min(desired_scale, cap)
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
) -> dict[str, Any] | None:
    ranked: list[tuple[float, int, str, dict[str, Any]]] = []
    for raw in candidates:
        if raw.get("blink") or raw.get("blur") or raw.get("hard_block"):
            continue
        ms = int(raw["ms"])
        rows = _samples(observations, ms, window_ms)
        crop = tuple(int(v) for v in selected_state["crop"])
        safe, _ = _crop_safe(rows, crop, width, height, float(selected_state["scale"]))
        if not safe:
            continue
        proximity = max(0.0, 1.0 - abs(ms - event_ms) / 1500.0)
        score = proximity
        score += 0.25 if raw.get("word_boundary") else 0.0
        score += 0.20 if raw.get("pause") else 0.0
        score += 0.15 if raw.get("head_return") else 0.0
        ranked.append((round(score, 6), ms, str(raw.get("id", "")), raw))

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
    window_ms = int(config.get("window_ms", 1200))
    observations = sorted(list(payload.get("observations") or []), key=lambda o: int(o["t_ms"]))
    events = sorted(list(payload.get("semantic_events") or []), key=lambda e: (int(e["t_ms"]), str(e.get("id", ""))))

    current_state = "CONTEXT"
    current_crop = [0, 0, width, height]
    decisions: list[dict[str, Any]] = []

    for event in events:
        event_ms = int(event["t_ms"])
        desired = str(event.get("type") or _state_for_importance(float(event.get("importance", 0.0)))).upper()
        if desired not in STATE_LEVEL:
            desired = _state_for_importance(float(event.get("importance", 0.0)))

        rows = _samples(observations, event_ms, window_ms)
        states = _candidate_states(
            rows,
            width=width,
            height=height,
            intensity=intensity,
            quality_cap=quality_cap,
        )
        selected = _choose_state(states, desired)
        if selected is None:
            decisions.append({"event_ms": event_ms, "status": "KEEP", "reason": "no_safe_state"})
            continue

        boundary = _choose_boundary(
            event_ms,
            list(event.get("boundary_candidates") or []),
            observations,
            selected,
            width=width,
            height=height,
            window_ms=window_ms,
        )
        if boundary is None:
            decisions.append({"event_ms": event_ms, "status": "KEEP", "reason": "no_safe_boundary"})
            continue

        target_crop = list(selected["crop"])
        scale_delta = abs(selected["scale"] / max(width / current_crop[2], 1e-9) - 1.0)
        if target_crop == current_crop:
            motion = "hold"
        elif scale_delta < MIN_STEP[intensity] and float(event.get("importance", 0.0)) >= 0.75:
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
                "desired_state": desired,
                "motion": motion,
                "crop_start": list(current_crop),
                "crop_end": target_crop,
                "scale": selected["scale"],
                "available_states": [s["state"] for s in states],
                "why": "semantic_importance",
                "boundary_score": boundary["score"],
            }
        )
        current_state = selected["state"]
        current_crop = target_crop

    return {
        "version": "1.7-lite",
        "source": {"width": width, "height": height},
        "config": {"intensity": intensity, "window_ms": window_ms, "quality_cap": quality_cap},
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
