#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_STATE_CAP = {"CONTEXT": 1.00, "ARGUMENT": 1.12, "EMPHASIS": 1.20}
DEFAULT_ABSOLUTE_ZOOM_CAP = 1.20


def check(plan: dict[str, Any]) -> dict[str, Any]:
    width = int(plan["source"]["width"])
    height = int(plan["source"]["height"])
    config = dict(plan.get("config") or {})
    absolute_cap = min(float(config.get("absolute_zoom_cap", DEFAULT_ABSOLUTE_ZOOM_CAP)), DEFAULT_ABSOLUTE_ZOOM_CAP)
    state_caps = dict(DEFAULT_STATE_CAP)
    for state, value in dict(config.get("state_caps") or {}).items():
        state = str(state).upper()
        if state in state_caps:
            state_caps[state] = min(float(value), DEFAULT_ABSOLUTE_ZOOM_CAP)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, decision in enumerate(plan.get("decisions", [])):
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
        "planned_count": sum(1 for d in plan.get("decisions", []) if d.get("status") == "PLANNED"),
        "cadence_request_count": len(plan.get("cadence_requests", [])),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QC Montaj v1.7 Lite crop plan")
    parser.add_argument("plan_json")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    report = check(plan)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
