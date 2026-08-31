from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpegSegmentProgram, bind_sendcmd_file


def _seconds(ms: int) -> str:
    return f"{ms / 1000.0:.6f}"


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
