#!/usr/bin/env python3
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


def _commands(plan: dict[str, Any], hz: int = 10) -> str:
    lines: list[str] = []
    target = "thz"
    for decision in plan.get("decisions", []):
        if decision.get("status") != "PLANNED":
            continue
        start_ms = int(decision["start_ms"])
        end_ms = int(decision["end_ms"])
        start = [int(v) for v in decision["crop_start"]]
        end = [int(v) for v in decision["crop_end"]]
        motion = str(decision.get("motion", "step"))

        if motion == "hold":
            continue
        if motion == "step" or end_ms <= start_ms:
            keyframes = [(start_ms, end)]
        else:
            duration = max(1, end_ms - start_ms)
            steps = max(2, int(round(duration / 1000 * hz)))
            keyframes = []
            for index in range(steps + 1):
                alpha = index / steps
                t_ms = start_ms + int(round(duration * alpha))
                crop = [_lerp(a, b, alpha) for a, b in zip(start, end)]
                keyframes.append((t_ms, crop))

        for t_ms, crop in keyframes:
            stamp = f"{t_ms / 1000.0:.6f}"
            x, y, w, h = crop
            lines.extend(
                [
                    f"{stamp} crop@{target} w {w};",
                    f"{stamp} crop@{target} h {h};",
                    f"{stamp} crop@{target} x {x};",
                    f"{stamp} crop@{target} y {y};",
                ]
            )
    return "\n".join(lines) + ("\n" if lines else "")


def render(input_video: str, plan: dict[str, Any], output_video: str) -> None:
    width = int(plan["source"]["width"])
    height = int(plan["source"]["height"])
    initial = [0, 0, width, height]
    planned = [d for d in plan.get("decisions", []) if d.get("status") == "PLANNED"]
    if planned:
        initial = [int(v) for v in planned[0].get("crop_start", initial)]

    commands = _commands(plan)
    with tempfile.TemporaryDirectory(prefix="montaj_v17_lite_") as tmp:
        cmd_path = Path(tmp) / "crop.cmd"
        cmd_path.write_text(commands, encoding="utf-8")
        x, y, w, h = initial
        crop = f"crop@thz=w={w}:h={h}:x={x}:y={y}:exact=1"
        if commands:
            vf = f"sendcmd=f={cmd_path},{crop},scale={width}:{height}:flags=lanczos,setsar=1"
        else:
            vf = f"{crop},scale={width}:{height}:flags=lanczos,setsar=1"

        args = [
            "ffmpeg", "-y", "-i", input_video,
            "-vf", vf,
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_video,
        ]
        subprocess.run(args, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Montaj v1.7 Lite crop plan")
    parser.add_argument("input_video")
    parser.add_argument("plan_json")
    parser.add_argument("output_video")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    render(args.input_video, plan, args.output_video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
