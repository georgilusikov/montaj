#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_CAP = {"CONTEXT": 1.00, "ARGUMENT": 1.08, "EMPHASIS": 1.12}
DEFAULT_ABSOLUTE_ZOOM_CAP = 1.13

V176_STATE_CAP = {
    "CONTEXT": 1.00,
    "SOFT": 1.05,
    "ARGUMENT": 1.11,
    "EMPHASIS": 1.14,
}
V176_ABSOLUTE_ZOOM_CAP = 1.16

DEFAULT_MIN_HEADROOM_RATIO = 0.05
HEADROOM_TOLERANCE = 0.002
DEFAULT_REQUIRE_VISIBLE_AFTER_MS = 8000


def _is_visible_change(decision: dict[str, Any]) -> bool:
    return (
        decision.get("status") == "PLANNED"
        and str(decision.get("motion", "hold")) != "hold"
        and decision.get("crop_start") != decision.get("crop_end")
    )


def check(plan: dict[str, Any]) -> dict[str, Any]:
    width = int(plan["source"]["width"])
    height = int(plan["source"]["height"])
    duration_ms = int(plan.get("source", {}).get("duration_ms") or 0)
    config = dict(plan.get("config") or {})

    is_v176 = str(plan.get("version", "")).startswith("1.7.6")
    hard_absolute_cap = V176_ABSOLUTE_ZOOM_CAP if is_v176 else DEFAULT_ABSOLUTE_ZOOM_CAP
    absolute_cap = min(float(config.get("absolute_zoom_cap", hard_absolute_cap)), hard_absolute_cap)

    min_headroom_ratio = max(0.0, float(config.get("min_headroom_ratio", DEFAULT_MIN_HEADROOM_RATIO)))
    require_visible_after_ms = int(config.get("require_visible_framing_after_ms", DEFAULT_REQUIRE_VISIBLE_AFTER_MS))
    allow_no_visible = bool(config.get("allow_no_visible_framing", False))
    semantic_contract_required = bool(config.get("semantic_contract_required", True))

    state_caps = dict(V176_STATE_CAP if is_v176 else DEFAULT_STATE_CAP)
    for state, value in dict(config.get("state_caps") or {}).items():
        state = str(state).upper()
        if state in state_caps:
            state_caps[state] = min(float(value), hard_absolute_cap)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    decisions = list(plan.get("decisions", []))
    planned = [d for d in decisions if d.get("status") == "PLANNED"]
    visible = [d for d in decisions if _is_visible_change(d)]
    accent_intents = [
        d for d in decisions
        if str(d.get("desired_state", d.get("state", "CONTEXT"))).upper() in {"ARGUMENT", "EMPHASIS"}
    ]

    if semantic_contract_required and duration_ms >= require_visible_after_ms and not allow_no_visible:
        if not decisions:
            errors.append({
                "check": "missing_semantic_events",
                "duration_ms": duration_ms,
                "reason": "long spoken edit reached zoom QC without semantic decisions",
            })
        elif not visible:
            errors.append({
                "check": "no_visible_framing_changes",
                "duration_ms": duration_ms,
                "decision_count": len(decisions),
                "accent_intent_count": len(accent_intents),
                "reason": "semantic pass produced zero visible crop/zoom changes",
            })

    if accent_intents and not visible:
        errors.append({
            "check": "semantic_accent_became_noop",
            "accent_intent_count": len(accent_intents),
            "reason": "ARGUMENT/EMPHASIS intent exists but no visible framing decision survived",
        })

    for index, decision in enumerate(decisions):
        if decision.get("status") != "PLANNED":
            continue
        state = str(decision.get("state", "CONTEXT")).upper()
        state_cap = min(state_caps.get(state, absolute_cap), absolute_cap)
        ratchet = str(decision.get("ratchet") or "").lower()
        if is_v176:
            if ratchet == "ratchet_1":
                state_cap = min(max(state_cap, 1.11), absolute_cap)
            elif ratchet == "ratchet_2":
                state_cap = min(max(state_cap, 1.14), absolute_cap)
            elif ratchet == "ratchet_3":
                state_cap = min(max(state_cap, 1.16), absolute_cap)
        else:
            if ratchet == "ratchet_2":
                state_cap = min(max(state_cap, 1.12), absolute_cap)
            elif ratchet == "ratchet_3":
                state_cap = min(max(state_cap, 1.13), absolute_cap)
        end_scale = None

        for key in ("crop_start", "crop_end"):
            crop = [int(v) for v in decision[key]]
            if len(crop) != 4:
                errors.append({"index": index, "check": "crop_shape", "field": key})
                continue
            x, y, w, h = crop
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
                errors.append({"index": index, "check": "crop_bounds", "field": key, "crop": crop})
            if any(v % 2 for v in crop):
                warnings.append({"index": index, "check": "crop_even", "field": key, "crop": crop})
            scale = min(width / max(w, 1), height / max(h, 1))
            if scale < 0.999:
                errors.append({"index": index, "check": "scale_below_1", "field": key, "scale": scale})
            if key == "crop_end":
                end_scale = scale

        declared_scale = decision.get("scale")
        if declared_scale is not None and float(declared_scale) > state_cap + 0.005:
            errors.append({
                "index": index,
                "check": "zoom_too_aggressive",
                "state": state,
                "scale": float(declared_scale),
                "cap": state_cap,
            })
        if end_scale is not None and end_scale > state_cap + 0.01:
            errors.append({
                "index": index,
                "check": "crop_scale_too_aggressive",
                "state": state,
                "scale": round(end_scale, 4),
                "cap": state_cap,
            })

        headroom_ratio = decision.get("headroom_ratio")
        if headroom_ratio is not None and float(headroom_ratio) + HEADROOM_TOLERANCE < min_headroom_ratio:
            errors.append({
                "index": index,
                "check": "headroom_too_small",
                "headroom_ratio": float(headroom_ratio),
                "required": min_headroom_ratio,
            })

        motion = str(decision.get("motion", "hold"))
        if motion != "hold" and decision.get("crop_start") == decision.get("crop_end"):
            errors.append({"index": index, "check": "noop_zoom", "motion": motion})
        if int(decision.get("end_ms", 0)) < int(decision.get("start_ms", 0)):
            errors.append({"index": index, "check": "negative_duration"})
        if state == "CONTEXT" and decision.get("crop_end") != [0, 0, width, height]:
            errors.append({"index": index, "check": "context_not_source_frame"})
        if bool(decision.get("cadence_refresh")) and float(decision.get("scale", 1.0)) > 1.055:
            errors.append({
                "index": index,
                "check": "cadence_refresh_too_strong",
                "scale": float(decision.get("scale", 1.0)),
                "cap": 1.05,
            })

    for index, request in enumerate(plan.get("cadence_requests", [])):
        if request.get("semantic_trigger") is not False:
            errors.append({"index": index, "check": "cadence_request_must_be_nonsemantic"})
        warnings.append({
            "index": index,
            "check": "visual_gap_refresh_unresolved",
            "at_ms": int(request.get("at_ms", 0)),
            "preferred_action": request.get("preferred_action", "soft_framing_refresh"),
            "reason": request.get("reason"),
        })

    return {
        "version": "1.7.6-lite" if is_v176 else "1.7.5-lite",
        "stage": "pre-render-qc",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "decision_count": len(decisions),
        "planned_count": len(planned),
        "visible_change_count": len(visible),
        "accent_intent_count": len(accent_intents),
        "cadence_request_count": len(plan.get("cadence_requests", [])),
        "cadence_soft_change_count": sum(1 for d in planned if bool(d.get("cadence_refresh"))),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QC Montaj v1.7.x Lite crop plan")
    parser.add_argument("plan_json")
    parser.add_argument("--output-json", help="Persist QC receipt for pipeline_guard.py")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    report = check(plan)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
