#!/usr/bin/env python3
"""Extract deterministic visual evidence frames for agent/vision review.

The script does not pretend to "see" the frames. It creates a review package
around content jumpcuts and planned framing changes. A vision-capable agent must
open the extracted images and produce a review receipt consumed by pipeline_guard.py.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

VERSION = "1.7.2-lite"
DEFAULT_OFFSETS_MS = (-160, 0, 160)


def _visible(decision: dict[str, Any]) -> bool:
    return (
        decision.get("status") == "PLANNED"
        and str(decision.get("motion", "hold")) != "hold"
        and decision.get("crop_start") != decision.get("crop_end")
    )


def build_review_groups(
    zoom_plan: dict[str, Any],
    cleanup_plan: dict[str, Any] | None = None,
    *,
    offsets_ms: tuple[int, ...] = DEFAULT_OFFSETS_MS,
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def add(kind: str, at_ms: int, label: str, metadata: dict[str, Any] | None = None) -> None:
        at_ms = max(0, int(at_ms))
        key = (kind, at_ms)
        if key in seen:
            return
        seen.add(key)
        group_id = f"{kind}_{at_ms:08d}"
        groups.append({
            "id": group_id,
            "kind": kind,
            "at_ms": at_ms,
            "label": label,
            "required": True,
            "offsets_ms": list(offsets_ms),
            "metadata": metadata or {},
        })

    if cleanup_plan:
        for at_ms in cleanup_plan.get("content_cuts_ms", []) or []:
            add("jumpcut", int(at_ms), "content jumpcut")

    for decision in zoom_plan.get("decisions", []) or []:
        if not _visible(decision):
            continue
        add(
            "zoom",
            int(decision.get("start_ms", decision.get("event_ms", 0))),
            f"semantic framing: {decision.get('state', 'UNKNOWN')}",
            {
                "event_id": decision.get("event_id"),
                "state": decision.get("state"),
                "motion": decision.get("motion"),
                "scale": decision.get("scale"),
            },
        )

    for returned in zoom_plan.get("returns", []) or []:
        if returned.get("crop_start") == returned.get("crop_end"):
            continue
        add(
            "return",
            int(returned.get("start_ms", 0)),
            "return to context framing",
            {"parent_event_id": returned.get("parent_event_id")},
        )

    groups.sort(key=lambda g: (int(g["at_ms"]), str(g["kind"]), str(g["id"])))
    return groups


def _extract_frame(video: str | Path, at_ms: int, output: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required for visual evidence extraction")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-ss", f"{max(0, at_ms) / 1000.0:.6f}",
        "-i", str(video),
        "-vf", "scale=720:-2:force_original_aspect_ratio=decrease",
        "-frames:v", "1",
        "-q:v", "2",
        str(output),
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError(
            f"frame extraction failed at {at_ms}ms: "
            f"{result.stderr.decode(errors='replace')[:300]}"
        )


def extract_review_package(
    video: str | Path,
    zoom_plan: dict[str, Any],
    output_dir: str | Path,
    *,
    cleanup_plan: dict[str, Any] | None = None,
    phase: str = "pre",
) -> dict[str, Any]:
    if phase not in {"pre", "final"}:
        raise ValueError("phase must be pre or final")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups = build_review_groups(zoom_plan, cleanup_plan)
    rendered: list[dict[str, Any]] = []

    for group in groups:
        frames: list[dict[str, Any]] = []
        for offset in group["offsets_ms"]:
            at_ms = max(0, int(group["at_ms"]) + int(offset))
            filename = f"{group['id']}_{int(offset):+05d}ms.jpg".replace("+", "p").replace("-", "m")
            path = out / filename
            _extract_frame(video, at_ms, path)
            frames.append({
                "offset_ms": int(offset),
                "at_ms": at_ms,
                "path": str(path),
            })
        item = dict(group)
        item["frames"] = frames
        rendered.append(item)

    manifest = {
        "version": VERSION,
        "phase": phase,
        "video": str(video),
        "review_group_count": len(rendered),
        "required_group_ids": [g["id"] for g in rendered if g.get("required", True)],
        "groups": rendered,
        "review_contract": {
            "instruction": "A vision-capable agent must open the extracted images before writing the receipt.",
            "receipt_status": "PASS only if every required group was visually inspected and no rejected group remains.",
        },
    }
    manifest_path = out / "visual_evidence.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract frames that must be visually reviewed")
    parser.add_argument("video")
    parser.add_argument("zoom_plan_json")
    parser.add_argument("output_dir")
    parser.add_argument("--cleanup-plan")
    parser.add_argument("--phase", choices=("pre", "final"), default="pre")
    args = parser.parse_args(argv)

    zoom_plan = json.loads(Path(args.zoom_plan_json).read_text(encoding="utf-8"))
    cleanup = None
    if args.cleanup_plan:
        cleanup = json.loads(Path(args.cleanup_plan).read_text(encoding="utf-8"))
    manifest = extract_review_package(
        args.video,
        zoom_plan,
        args.output_dir,
        cleanup_plan=cleanup,
        phase=args.phase,
    )
    print(json.dumps({
        "status": "PASS" if manifest["review_group_count"] else "FAIL",
        "phase": args.phase,
        "review_group_count": manifest["review_group_count"],
        "manifest": str(Path(args.output_dir) / "visual_evidence.json"),
    }, ensure_ascii=False))
    return 0 if manifest["review_group_count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
