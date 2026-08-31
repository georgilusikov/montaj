from __future__ import annotations

import argparse
import json
from pathlib import Path

from thz_planner.manifest_io import manifest_from_planner_output
from thz_planner.schema import canonical_json

from .ffmpeg import compile_ffmpeg_timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile v1.7.1 planner JSON into a deterministic FFmpeg timeline program")
    parser.add_argument("input", type=Path, help="Planner output JSON or bare manifest JSON")
    parser.add_argument("output", type=Path, help="Canonical renderer program JSON")
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--source-w", type=int, required=True)
    parser.add_argument("--source-h", type=int, required=True)
    parser.add_argument("--output-w", type=int, default=1080)
    parser.add_argument("--output-h", type=int, default=1920)
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    manifest = manifest_from_planner_output(payload)
    program = compile_ffmpeg_timeline(
        manifest,
        fps=args.fps,
        source_w=args.source_w,
        source_h=args.source_h,
        output_w=args.output_w,
        output_h=args.output_h,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(program) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
