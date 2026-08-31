#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def check(plan: dict[str, Any]) -> dict[str, Any]:
    width = int(plan["source"]["width"])
    height = int(plan["source"]["height"])
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for index, decision in enumerate(plan.get("decisions", [])):
        if decision.get("status") != "PLANNED":
            continue
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

        motion = str(decision.get("motion", "hold"))
        if motion != "hold" and decision.get("crop_start") == decision.get("crop_end"):
            errors.append({"index": index, "check": "noop_zoom", "motion": motion})
        if int(decision.get("end_ms", 0)) < int(decision.get("start_ms", 0)):
            errors.append({"index": index, "check": "negative_duration"})

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "planned_count": sum(1 for d in plan.get("decisions", []) if d.get("status") == "PLANNED"),
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
