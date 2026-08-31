#!/usr/bin/env python3
"""
Source Normalization Pass for Montaj Talking-Head Pipeline.
Handles:
1. Physical rotation from metadata.
2. VFR to CFR conversion (e.g., 30 fps).
3. HDR / HLG / Dolby Vision tonemapping to BT.709 SDR.
4. Pixel format conversion to yuv420p.
5. Apple ColorSync metadata tagging (-movflags +write_colr, BT.709 NCLC).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def probe_video(input_path: str | Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def build_normalization_cmd(
    input_path: str | Path,
    output_path: str | Path,
    target_fps: int = 30,
    force_rec709: bool = True,
) -> list[str]:
    probe = probe_video(input_path)
    video_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise ValueError(f"No video stream found in {input_path}")

    pix_fmt = video_stream.get("pix_fmt", "")
    color_space = video_stream.get("color_space", "")
    color_transfer = video_stream.get("color_transfer", "")
    color_primaries = video_stream.get("color_primaries", "")

    # Check if HDR / 10-bit
    is_hdr = (
        "10" in pix_fmt
        or color_transfer in {"arib-std-b67", "smpte2084"}
        or color_primaries in {"bt2020"}
    )

    filters: list[str] = [f"fps=fps={target_fps}"]

    if is_hdr and force_rec709:
        # High quality mobius tonemapping to BT.709 SDR
        filters.append(
            "zscale=tin=arib-std-b67:pin=bt2020:min=bt2020:t=bt709:p=bt709:m=bt709:r=tv,tonemap=tonemap=mobius:param=0.3,format=yuv420p"
        )
    else:
        filters.append("format=yuv420p")

    vf_chain = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", vf_chain,
        "-vsync", "cfr",
        "-c:v", "libx264",
        "-crf", "17",
        "-preset", "medium",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-c:a", "pcm_s16le",
        "-movflags", "+faststart+write_colr",
        str(output_path),
    ]
    return cmd


def normalize_source(
    input_path: str | Path,
    output_path: str | Path,
    target_fps: int = 30,
) -> None:
    cmd = build_normalization_cmd(input_path, output_path, target_fps=target_fps)
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize input video to standard CFR Rec.709")
    parser.add_argument("input_video", help="Raw input video (.mp4, .mov, etc.)")
    parser.add_argument("output_video", help="Normalized CFR Rec.709 output video")
    parser.add_argument("--fps", type=int, default=30, help="Target constant frame rate (default: 30)")
    args = parser.parse_args(argv)

    normalize_source(args.input_video, args.output_video, target_fps=args.fps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
