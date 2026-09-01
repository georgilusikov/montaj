#!/usr/bin/env python3
"""
Post-render verification for Montaj v1.7.1 Lite.

For each visible semantic framing decision, compare the rendered frame with the
frame that should result from applying the decision's crop to dense.mp4.
This catches "planner says zoom, final.mp4 stayed at 100%" regressions.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROBE_W = 96
PROBE_H = 170
DEFAULT_MAX_MAE = 5.0


def _extract_gray_frame(
    video: str | Path,
    at_ms: int,
    *,
    crop: list[int] | None = None,
    source_size: tuple[int, int] | None = None,
) -> bytes:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for post-render QC")

    vf: list[str] = []
    if crop is not None:
        x, y, w, h = [int(v) for v in crop]
        vf.append(f"crop={w}:{h}:{x}:{y}:exact=1")
        if source_size is None:
            raise ValueError("source_size is required when crop is supplied")
        sw, sh = source_size
        vf.append(f"scale={sw}:{sh}:flags=lanczos")
    vf.extend([
        f"scale={PROBE_W}:{PROBE_H}:flags=lanczos",
        "format=gray",
    ])

    args = [
        "ffmpeg", "-v", "error",
        "-ss", f"{max(0, at_ms) / 1000.0:.6f}",
        "-i", str(video),
        "-vf", ",".join(vf),
        "-frames:v", "1",
        "-f", "rawvideo",
        "-pix_fmt", "gray",
        "pipe:1",
    ]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    expected = PROBE_W * PROBE_H
    if result.returncode != 0 or len(result.stdout) != expected:
        raise RuntimeError(
            f"ffmpeg frame probe failed for {video} at {at_ms}ms: "
            f"rc={result.returncode}, bytes={len(result.stdout)}, stderr={result.stderr.decode(errors='replace')[:300]}"
        )
    return result.stdout


def _mae(a: bytes, b: bytes) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("frame buffers must be non-empty and equal length")
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _visible_decisions(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        d for d in plan.get("decisions", [])
        if d.get("status") == "PLANNED"
        and str(d.get("motion", "hold")) != "hold"
        and d.get("crop_start") != d.get("crop_end")
    ]


def _probe_time(decision: dict[str, Any]) -> int:
    start = int(decision.get("start_ms", 0))
    end = int(decision.get("end_ms", start))
    transition_end = int(decision.get("transition_end_ms", start))
    candidate = max(start + 120, transition_end + 120)
    if end > start:
        candidate = min(candidate, max(start, end - 80))
    return max(start, candidate)


def verify(
    input_video: str | Path,
    final_video: str | Path,
    plan: dict[str, Any],
    *,
    max_mae: float = DEFAULT_MAX_MAE,
) -> dict[str, Any]:
    source = dict(plan.get("source") or {})
    width = int(source["width"])
    height = int(source["height"])
    visible = _visible_decisions(plan)

    errors: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []

    if not Path(final_video).is_file() or Path(final_video).stat().st_size == 0:
        return {
            "status": "FAIL",
            "errors": [{"check": "final_missing"}],
            "probes": [],
            "visible_change_count": len(visible),
        }

    if not visible:
        return {
            "status": "FAIL",
            "errors": [{"check": "no_visible_plan_to_verify"}],
            "probes": [],
            "visible_change_count": 0,
        }

    for index, decision in enumerate(visible):
        at_ms = _probe_time(decision)
        try:
            expected = _extract_gray_frame(
                input_video,
                at_ms,
                crop=[int(v) for v in decision["crop_end"]],
                source_size=(width, height),
            )
            actual = _extract_gray_frame(final_video, at_ms)
            error = _mae(expected, actual)
        except Exception as exc:
            errors.append({
                "index": index,
                "check": "frame_probe_failed",
                "at_ms": at_ms,
                "detail": str(exc),
            })
            continue

        probe = {
            "index": index,
            "event_id": decision.get("event_id"),
            "at_ms": at_ms,
            "state": decision.get("state"),
            "scale": decision.get("scale"),
            "mae": round(error, 4),
            "max_mae": max_mae,
        }
        probes.append(probe)
        if error > max_mae:
            errors.append({
                "index": index,
                "check": "render_does_not_match_planned_crop",
                "at_ms": at_ms,
                "mae": round(error, 4),
                "max_mae": max_mae,
                "event_id": decision.get("event_id"),
            })

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "probes": probes,
        "visible_change_count": len(visible),
        "verified_change_count": sum(1 for p in probes if p["mae"] <= max_mae),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify rendered Montaj framing against zoom_plan.json")
    parser.add_argument("dense_video")
    parser.add_argument("final_video")
    parser.add_argument("plan_json")
    parser.add_argument("--max-mae", type=float, default=DEFAULT_MAX_MAE)
    args = parser.parse_args(argv)

    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    report = verify(args.dense_video, args.final_video, plan, max_mae=args.max_mae)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
