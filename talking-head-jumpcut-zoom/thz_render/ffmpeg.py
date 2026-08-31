from __future__ import annotations

from dataclasses import dataclass
import re

from .contract import RenderSegmentPlan


@dataclass(frozen=True)
class FFmpegSegmentProgram:
    segment_id: str
    filtergraph_template: str
    sendcmd_text: str | None
    command_file_token: str | None


def _target_id(segment_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", segment_id)
    return f"thz_{cleaned or 'segment'}"


def _validate_plan_bounds(plan: RenderSegmentPlan, source_w: int, source_h: int) -> None:
    for keyframe in plan.keyframes:
        crop = keyframe.crop
        if crop.x < 0 or crop.y < 0 or crop.w <= 0 or crop.h <= 0:
            raise ValueError("invalid canonical crop")
        if crop.x + crop.w > source_w or crop.y + crop.h > source_h:
            raise ValueError("canonical crop exceeds source bounds")
        if any(value % 2 for value in (crop.x, crop.y, crop.w, crop.h)):
            raise ValueError("FFmpeg canonical crop must use even integers")


def _command_lines(plan: RenderSegmentPlan, target: str) -> list[str]:
    lines: list[str] = []
    for keyframe in plan.keyframes[1:]:
        seconds = (keyframe.t_ms - plan.start_ms) / 1000.0
        if seconds < 0:
            raise ValueError("keyframe precedes segment start")
        stamp = f"{seconds:.6f}"
        crop = keyframe.crop
        lines.extend((
            f"{stamp} crop@{target} w {crop.w};",
            f"{stamp} crop@{target} h {crop.h};",
            f"{stamp} crop@{target} x {crop.x};",
            f"{stamp} crop@{target} y {crop.y};",
        ))
    return lines


def compile_ffmpeg_segment(
    plan: RenderSegmentPlan,
    *,
    source_w: int,
    source_h: int,
    output_w: int = 1080,
    output_h: int = 1920,
) -> FFmpegSegmentProgram:
    """Compile exact canonical crops to an FFmpeg crop/sendcmd program.

    The caller applies this filter to an already content-edited segment whose local
    t=0 corresponds to plan.start_ms. `{sendcmd_file}` is intentionally a token so
    filesystem policy stays outside the deterministic compiler.
    """
    if not plan.keyframes:
        raise ValueError("render segment requires at least one keyframe")
    if source_w <= 0 or source_h <= 0 or output_w <= 0 or output_h <= 0:
        raise ValueError("dimensions must be positive")
    _validate_plan_bounds(plan, source_w, source_h)

    target = _target_id(plan.segment_id)
    initial = plan.keyframes[0].crop
    crop_filter = (
        f"crop@{target}=w={initial.w}:h={initial.h}:x={initial.x}:y={initial.y}:exact=1"
    )
    tail = f"scale={output_w}:{output_h}:flags=lanczos,setsar=1"
    commands = _command_lines(plan, target)
    if not commands:
        return FFmpegSegmentProgram(
            segment_id=plan.segment_id,
            filtergraph_template=f"{crop_filter},{tail}",
            sendcmd_text=None,
            command_file_token=None,
        )

    token = "{sendcmd_file}"
    return FFmpegSegmentProgram(
        segment_id=plan.segment_id,
        filtergraph_template=f"sendcmd=f={token},{crop_filter},{tail}",
        sendcmd_text="\n".join(commands) + "\n",
        command_file_token=token,
    )


def bind_sendcmd_file(program: FFmpegSegmentProgram, path: str) -> str:
    if program.command_file_token is None:
        return program.filtergraph_template
    if not path:
        raise ValueError("sendcmd path required")
    # FFmpeg filtergraph escaping is backend-specific; reject characters that would
    # require ambiguous inline escaping and let the caller choose a safe temp path.
    if any(char in path for char in ",;'\n\r"):
        raise ValueError("sendcmd path contains unsupported filtergraph characters")
    return program.filtergraph_template.replace(program.command_file_token, path)
