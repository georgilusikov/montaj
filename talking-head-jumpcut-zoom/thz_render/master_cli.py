from __future__ import annotations

import argparse
import json
from pathlib import Path

from thz_planner.manifest_io import manifest_from_planner_output
from thz_planner.schema import canonical_json

from .execution import execute_video_timeline, probe_video
from .ffmpeg import compile_ffmpeg_timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a deterministic v1.7.1 video-only master from planner JSON"
    )
    parser.add_argument("planner_json", type=Path)
    parser.add_argument("source_video", type=Path)
    parser.add_argument("output_video", type=Path)
    parser.add_argument("--output-w", type=int, default=None)
    parser.add_argument("--output-h", type=int, default=None)
    parser.add_argument("--program-output", type=Path, default=None)
    parser.add_argument("--preset", default="ultrafast")
    parser.add_argument("--crf", type=int, default=18)
    args = parser.parse_args(argv)

    payload = json.loads(args.planner_json.read_text(encoding="utf-8"))
    manifest = manifest_from_planner_output(payload)
    probe = probe_video(args.source_video)
    output_w = args.output_w if args.output_w is not None else probe.width
    output_h = args.output_h if args.output_h is not None else probe.height

    timeline = compile_ffmpeg_timeline(
        manifest,
        fps=probe.fps,
        source_w=probe.width,
        source_h=probe.height,
        output_w=output_w,
        output_h=output_h,
    )
    if args.program_output is not None:
        args.program_output.parent.mkdir(parents=True, exist_ok=True)
        args.program_output.write_text(canonical_json(timeline) + "\n", encoding="utf-8")

    execute_video_timeline(
        timeline,
        input_path=args.source_video,
        output_path=args.output_video,
        preset=str(args.preset),
        crf=int(args.crf),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
