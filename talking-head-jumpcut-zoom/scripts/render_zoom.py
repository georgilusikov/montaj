#!/usr/bin/env python3
"""Montaj v1.7.2 Motion & Crop Renderer.

Executes exact pixel crops from zoom_plan.json. Production CLI execution is
locked behind a PASS receipt from pipeline_guard.py so an agent cannot silently
skip semantics/perception/visual review and still call the canonical renderer.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _lerp(a: int, b: int, alpha: float) -> int:
    value = int(round(a + (b - a) * alpha))
    return value if value % 2 == 0 else value - 1


def _ease(alpha: float) -> float:
    alpha = max(0.0, min(1.0, alpha))
    return alpha * alpha * (3.0 - 2.0 * alpha)


def _timeline_items(plan: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for decision in plan.get("decisions", []):
        if decision.get("status") == "PLANNED":
            item = dict(decision)
            item["_priority"] = 1
            items.append(item)
    for returned in plan.get("returns", []):
        item = dict(returned)
        item["_priority"] = 0
        items.append(item)
    items.sort(key=lambda item: (int(item.get("start_ms", 0)), int(item.get("_priority", 1))))
    return items


def _commands(plan: dict[str, Any], hz: int = 60) -> str:
    target = "thz"
    keyframes: list[tuple[int, int, list[int]]] = []
    sequence = 0
    for decision in _timeline_items(plan):
        start_ms = int(decision["start_ms"])
        start = [int(v) for v in decision["crop_start"]]
        end = [int(v) for v in decision["crop_end"]]
        motion = str(decision.get("motion", "step"))
        if motion == "hold":
            continue
        if motion == "step":
            sequence += 1
            keyframes.append((start_ms, sequence, end))
            continue
        transition_end_ms = int(decision.get("transition_end_ms", decision.get("end_ms", start_ms)))
        if transition_end_ms <= start_ms:
            sequence += 1
            keyframes.append((start_ms, sequence, end))
            continue
        duration = transition_end_ms - start_ms
        steps = max(2, int(round(duration / 1000 * hz)))
        for index in range(steps + 1):
            raw_alpha = index / steps
            alpha = _ease(raw_alpha)
            t_ms = start_ms + int(round(duration * raw_alpha))
            crop = [_lerp(a, b, alpha) for a, b in zip(start, end)]
            sequence += 1
            keyframes.append((t_ms, sequence, crop))

    keyframes.sort(key=lambda item: (item[0], item[1]))
    lines: list[str] = []
    for t_ms, _, crop in keyframes:
        stamp = f"{t_ms / 1000.0:.6f}"
        x, y, w, h = crop
        lines.extend([
            f"{stamp} crop@{target} w {w};",
            f"{stamp} crop@{target} h {h};",
            f"{stamp} crop@{target} x {x};",
            f"{stamp} crop@{target} y {y};",
        ])
    return "\n".join(lines) + ("\n" if lines else "")


def validate_guard(report: dict[str, Any]) -> None:
    if str(report.get("stage", "")).lower() != "pre-render":
        raise ValueError("render requires a pre-render pipeline_guard receipt")
    if str(report.get("status", "")).upper() != "PASS":
        raise ValueError("pipeline_guard status is not PASS")
    if str(report.get("pipeline_lock", "")).upper() != "PASS":
        raise ValueError("pipeline_lock is not PASS")
    if str(report.get("visual_evidence", "")).upper() != "PASS":
        raise ValueError("visual evidence gate is not PASS")


def render(
    input_video: str,
    plan: dict[str, Any],
    output_video: str,
    *,
    encoder_preset: str = "fast",
) -> None:
    if encoder_preset not in {"veryfast", "fast", "medium", "slow"}:
        raise ValueError("unsupported libx264 preset")
    width = int(plan["source"]["width"])
    height = int(plan["source"]["height"])
    initial = [0, 0, width, height]
    timeline = _timeline_items(plan)
    if timeline:
        initial = [int(v) for v in timeline[0].get("crop_start", initial)]

    commands = _commands(plan)
    with tempfile.TemporaryDirectory(prefix="montaj_v172_") as tmp:
        cmd_path = Path(tmp) / "crop.cmd"
        cmd_path.write_text(commands, encoding="utf-8")
        x, y, w, h = initial
        crop = f"crop@thz=w={w}:h={h}:x={x}:y={y}:exact=1"
        if commands:
            vf = f"sendcmd=f={cmd_path},{crop},scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p"
        else:
            vf = f"{crop},scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p"

        af = "loudnorm=I=-14:TP=-1.5:LRA=11"
        args = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", vf,
            "-af", af,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "17", "-preset", encoder_preset,
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart+write_colr",
            "-progress", "pipe:2", "-nostats",
            output_video,
        ]
        # Deliberately do not capture stderr: the agent must see real out_time/speed.
        subprocess.run(args, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Montaj v1.7.2 crop plan")
    parser.add_argument("input_video")
    parser.add_argument("plan_json")
    parser.add_argument("output_video")
    parser.add_argument("--guard-report", help="PASS receipt produced by pipeline_guard.py pre-render")
    parser.add_argument("--encoder-preset", choices=("veryfast", "fast", "medium", "slow"), default="fast")
    parser.add_argument(
        "--unsafe-bypass-pipeline-lock",
        action="store_true",
        help="Debug/unit use only. Forbidden for production skill runs.",
    )
    args = parser.parse_args(argv)

    if not args.unsafe_bypass_pipeline_lock:
        if not args.guard_report:
            parser.error("--guard-report is required for production render")
        guard = json.loads(Path(args.guard_report).read_text(encoding="utf-8"))
        validate_guard(guard)

    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    render(args.input_video, plan, args.output_video, encoder_preset=args.encoder_preset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
