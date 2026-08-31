from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from thz_planner.schema import CanonicalCrop, FramingDecision, RenderPrimitive


@dataclass(frozen=True)
class RenderKeyframe:
    t_ms: int
    crop: CanonicalCrop


@dataclass(frozen=True)
class RenderSegmentPlan:
    segment_id: str
    start_ms: int
    end_ms: int
    primitive: RenderPrimitive
    keyframes: tuple[RenderKeyframe, ...]


def _even_round(value: float) -> int:
    n = int(round(value))
    return n if n % 2 == 0 else n - 1


def _interpolate_crop(a: CanonicalCrop, b: CanonicalCrop, alpha: float) -> CanonicalCrop:
    alpha = max(0.0, min(1.0, alpha))
    return CanonicalCrop(
        x=_even_round(a.x + (b.x - a.x) * alpha),
        y=_even_round(a.y + (b.y - a.y) * alpha),
        w=max(2, _even_round(a.w + (b.w - a.w) * alpha)),
        h=max(2, _even_round(a.h + (b.h - a.h) * alpha)),
    )


def compile_framing_keyframes(
    decision: FramingDecision,
    *,
    fps: float,
) -> tuple[RenderKeyframe, ...]:
    """Compile canonical framing into deterministic crop keyframes.

    This layer does not re-solve geometry. It only samples the canonical endpoint
    crops already chosen by the planner. A concrete FFmpeg backend can later encode
    these keyframes with sendcmd/zoompan or another equivalent primitive.
    """
    if fps <= 0:
        raise ValueError("fps must be positive")
    if decision.time_basis != "output":
        raise ValueError("renderer requires output-time framing decisions")
    if decision.end_ms < decision.start_ms:
        raise ValueError("invalid framing range")

    if decision.primitive in {RenderPrimitive.HOLD, RenderPrimitive.STEP}:
        # STEP is already resolved at the boundary: the segment itself holds the
        # new crop. There is no hidden interpolation after the cut/reframe.
        return (RenderKeyframe(decision.start_ms, decision.crop_end),)

    duration_ms = int(decision.derived.get("motion_duration_ms", 0))
    if duration_ms <= 0:
        return (RenderKeyframe(decision.start_ms, decision.crop_end),)

    duration_ms = min(duration_ms, decision.end_ms - decision.start_ms)
    frame_ms = 1000.0 / fps
    frame_count = max(1, int(round(duration_ms / frame_ms)))
    frames: list[RenderKeyframe] = []
    for index in range(frame_count + 1):
        alpha = index / frame_count
        t_ms = decision.start_ms + int(round(duration_ms * alpha))
        frames.append(
            RenderKeyframe(
                t_ms=t_ms,
                crop=_interpolate_crop(decision.crop_start, decision.crop_end, alpha),
            )
        )

    # Preserve exact canonical endpoints after integer interpolation.
    frames[0] = RenderKeyframe(decision.start_ms, decision.crop_start)
    frames[-1] = RenderKeyframe(decision.start_ms + duration_ms, decision.crop_end)
    return tuple(frames)


def compile_render_plan(
    manifest: dict[str, Any],
    *,
    fps: float,
) -> tuple[RenderSegmentPlan, ...]:
    framing = manifest.get("framing_decisions", ())
    plans: list[RenderSegmentPlan] = []
    for decision in framing:
        keyframes = compile_framing_keyframes(decision, fps=fps)
        plans.append(
            RenderSegmentPlan(
                segment_id=decision.segment_id,
                start_ms=decision.start_ms,
                end_ms=decision.end_ms,
                primitive=decision.primitive,
                keyframes=keyframes,
            )
        )
    return tuple(sorted(plans, key=lambda p: (p.start_ms, p.segment_id)))
