from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile

from .ffmpeg import FFmpegSegmentProgram, FFmpegTimelineProgram, bind_sendcmd_file


@dataclass(frozen=True)
class VideoProbe:
    width: int
    height: int
    fps: float


def _seconds(ms: int) -> str:
    return f"{ms / 1000.0:.6f}"


def _rate(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        denominator = float(den)
        if denominator == 0:
            raise ValueError("invalid ffprobe frame rate")
        return float(num) / denominator
    return float(value)


def probe_video(path: str | Path) -> VideoProbe:
    source = Path(path)
    if not source.is_file():
        raise ValueError("source video does not exist")
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(source),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(completed.stdout)
    streams = list(payload.get("streams") or [])
    if len(streams) != 1:
        raise ValueError("source must expose exactly one selected video stream")
    stream = streams[0]
    width = int(stream["width"])
    height = int(stream["height"])
    rate = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0")
    fps = _rate(rate)
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("invalid source video probe")
    return VideoProbe(width=width, height=height, fps=round(fps, 6))


def ffmpeg_segment_command(
    program: FFmpegSegmentProgram,
    *,
    input_path: str | Path,
    output_path: str | Path,
    sendcmd_path: str | Path | None = None,
    video_codec: str = "libx264",
    preset: str = "ultrafast",
    crf: int = 18,
) -> list[str]:
    """Build argv for one exact kept-source/framing segment.

    This is intentionally video-only. Audio/speech-integrity assembly remains a
    separate pipeline responsibility; the framing renderer must not silently alter
    that contract.
    """
    if program.source_start_ms is None or program.source_end_ms is None:
        raise ValueError("timeline source mapping required before execution")
    if program.source_end_ms < program.source_start_ms:
        raise ValueError("source end precedes start")
    duration_ms = program.source_end_ms - program.source_start_ms
    if duration_ms <= 0:
        raise ValueError("zero-duration renderer segment is not executable")

    if program.sendcmd_text is not None:
        if sendcmd_path is None:
            raise ValueError("dynamic renderer segment requires sendcmd_path")
        filtergraph = bind_sendcmd_file(program, str(sendcmd_path))
    else:
        filtergraph = program.filtergraph_template

    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        _seconds(program.source_start_ms),
        "-t",
        _seconds(duration_ms),
        "-i",
        str(input_path),
        "-vf",
        filtergraph,
        "-an",
        "-c:v",
        video_codec,
        "-preset",
        preset,
        "-crf",
        str(int(crf)),
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]


def write_sendcmd_file(program: FFmpegSegmentProgram, path: str | Path) -> None:
    if program.sendcmd_text is None:
        raise ValueError("segment has no sendcmd program")
    Path(path).write_text(program.sendcmd_text, encoding="utf-8")


def concat_list_text(paths: list[str | Path]) -> str:
    """Build an ffconcat list for controlled temp paths.

    Reject quotes/newlines rather than attempting ambiguous shell/demuxer escaping.
    """
    rows: list[str] = []
    for path in paths:
        value = str(path)
        if not value or any(char in value for char in "'\n\r"):
            raise ValueError("unsupported concat path")
        rows.append(f"file '{value}'")
    if not rows:
        raise ValueError("concat requires at least one segment")
    return "\n".join(rows) + "\n"


def ffmpeg_concat_command(
    *,
    concat_list_path: str | Path,
    output_path: str | Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-c",
        "copy",
        str(output_path),
    ]


def _run(args: list[str]) -> None:
    subprocess.run(
        args,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def execute_video_timeline(
    timeline: FFmpegTimelineProgram,
    *,
    input_path: str | Path,
    output_path: str | Path,
    video_codec: str = "libx264",
    preset: str = "ultrafast",
    crf: int = 18,
) -> None:
    """Render and concatenate a complete deterministic video-only timeline."""
    source = Path(input_path)
    if not source.is_file():
        raise ValueError("source video does not exist")
    if not timeline.segments:
        raise ValueError("renderer timeline has no segments")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="thz_render_") as tmp:
        root = Path(tmp)
        rendered: list[Path] = []
        for index, program in enumerate(timeline.segments):
            segment_path = root / f"segment_{index:05d}.mp4"
            sendcmd_path = None
            if program.sendcmd_text is not None:
                sendcmd_path = root / f"commands_{index:05d}.txt"
                write_sendcmd_file(program, sendcmd_path)
            _run(
                ffmpeg_segment_command(
                    program,
                    input_path=source,
                    output_path=segment_path,
                    sendcmd_path=sendcmd_path,
                    video_codec=video_codec,
                    preset=preset,
                    crf=crf,
                )
            )
            rendered.append(segment_path)

        concat_path = root / "concat.txt"
        concat_path.write_text(concat_list_text(rendered), encoding="utf-8")
        _run(ffmpeg_concat_command(concat_list_path=concat_path, output_path=target))
