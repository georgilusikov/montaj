#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_CAP = {"CONTEXT": 1.00, "ARGUMENT": 1.12, "EMPHASIS": 1.20}
DEFAULT_ABSOLUTE_ZOOM_CAP = 1.20
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
    absolute_cap = min(float(config.get("absolute_zoom_cap", DEFAULT_ABSOLUTE_ZOOM_CAP)), DEFAULT_ABSOLUTE_ZOOM_CAP)
    require_visible_after_ms = int(config.get("require_visible_framing_after_ms", DEFAULT_REQUIRE_VISIBLE_AFTER_MS))
    allow_no_visible = bool(config.get("allow_no_visible_framing", False))
    # Production is fail-closed by default. Unit/planner-only calls must opt out explicitly.
    semantic_contract_required = bool(config.get("semantic_contract_required", True))

    state_caps = dict(DEFAULT_STATE_CAP)
    for state, value in dict(config.get("state_caps") or {}).items():
        state = str(state).upper()
        if state in state_caps:
            state_caps[state] = min(float(value), DEFAULT_ABSOLUTE_ZOOM_CAP)

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

    # Once ARGUMENT/EMPHASIS intent exists, a complete collapse to zero visible
    # changes is never a successful zoom plan, even in planner-only mode.
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
        if ratchet == "ratchet_2":
            state_cap = min(max(state_cap, 1.16), absolute_cap)
        elif ratchet == "ratchet_3":
            state_cap = min(max(state_cap, 1.20), absolute_cap)
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

        motion = str(decision.get("motion", "hold"))
        if motion != "hold" and decision.get("crop_start") == decision.get("crop_end"):
            errors.append({"index": index, "check": "noop_zoom", "motion": motion})
        if int(decision.get("end_ms", 0)) < int(decision.get("start_ms", 0)):
            errors.append({"index": index, "check": "negative_duration"})
        if state == "CONTEXT" and decision.get("crop_end") != [0, 0, width, height]:
            errors.append({"index": index, "check": "context_not_source_frame"})

    for index, request in enumerate(plan.get("cadence_requests", [])):
        if request.get("semantic_trigger") is not False:
            errors.append({"index": index, "check": "cadence_request_must_be_nonsemantic"})
        warnings.append({
            "index": index,
            "check": "visual_gap_requires_jumpcut",
            "at_ms": int(request.get("at_ms", 0)),
            "preferred_action": request.get("preferred_action", "jumpcut_same_scale"),
        })

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "decision_count": len(decisions),
        "planned_count": len(planned),
        "visible_change_count": len(visible),
        "accent_intent_count": len(accent_intents),
        "cadence_request_count": len(plan.get("cadence_requests", [])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QC Montaj v1.7.1 Lite crop plan")
    parser.add_argument("plan_json")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    report = check(plan)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
