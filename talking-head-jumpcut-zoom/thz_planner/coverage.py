from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .framing import canonical_crop_for_window
from .schema import (
    FramingDecision,
    FrameObservation,
    MotionIntent,
    QualityMetrics,
    RenderPrimitive,
    ShotState,
)
from .timeline import ContentEdit


SOURCE_BASE_TARGETS = {
    ShotState.CONTEXT: 0.30,
    ShotState.ARGUMENT: 0.355,
    ShotState.EMPHASIS: 0.41,
}


@dataclass(frozen=True)
class CoverageGap:
    content_segment_id: str
    start_ms: int
    end_ms: int
    time_basis: str


def _classify_source_base(observations: list[FrameObservation]) -> ShotState:
    if not observations:
        return ShotState.CONTEXT
    ratio = median(item.face_ratio for item in observations)
    return min(
        SOURCE_BASE_TARGETS,
        key=lambda state: (abs(SOURCE_BASE_TARGETS[state] - ratio), state.value),
    )


def _observations_for_range(
    observations: list[FrameObservation],
    start_ms: int,
    end_ms: int,
) -> list[FrameObservation]:
    selected = [item for item in observations if start_ms <= item.t_ms <= end_ms]
    if selected:
        return sorted(selected, key=lambda item: item.t_ms)
    if not observations:
        raise ValueError("observations required for coverage")
    nearest = min(
        observations,
        key=lambda item: (min(abs(item.t_ms - start_ms), abs(item.t_ms - end_ms)), item.t_ms),
    )
    return [nearest]


def source_coverage_gaps(
    content_edits: Iterable[ContentEdit],
    framing_decisions: Iterable[FramingDecision],
) -> tuple[CoverageGap, ...]:
    """Find uncovered kept source-time intervals using half-open coverage semantics."""
    content = tuple(sorted(content_edits, key=lambda item: (item.src_start_ms, item.segment_id)))
    framing = tuple(sorted(framing_decisions, key=lambda item: (item.start_ms, item.segment_id)))
    if any(item.time_basis != "source" for item in framing):
        raise ValueError("source_coverage_gaps requires source-time framing")

    gaps: list[CoverageGap] = []
    for edit in content:
        relevant = [
            item
            for item in framing
            if edit.src_start_ms <= item.start_ms <= item.end_ms <= edit.src_end_ms
        ]
        cursor = edit.src_start_ms
        for decision in relevant:
            if decision.start_ms < cursor:
                raise ValueError("framing decisions overlap while computing coverage")
            if cursor < decision.start_ms:
                gaps.append(CoverageGap(edit.segment_id, cursor, decision.start_ms, "source"))
            cursor = max(cursor, decision.end_ms)
        if cursor < edit.src_end_ms:
            gaps.append(CoverageGap(edit.segment_id, cursor, edit.src_end_ms, "source"))
    return tuple(gaps)


def output_coverage_gaps(manifest: dict[str, object]) -> tuple[CoverageGap, ...]:
    """Find renderer-facing gaps over each kept output interval."""
    content = tuple(manifest.get("content_edits", ()))
    framing = tuple(manifest.get("framing_decisions", ()))
    gaps: list[CoverageGap] = []
    for edit in sorted(content, key=lambda item: (item.out_start_ms, item.segment_id)):
        relevant = [
            item
            for item in framing
            if edit.out_start_ms <= item.start_ms <= item.end_ms <= edit.out_end_ms
        ]
        cursor = edit.out_start_ms
        for decision in relevant:
            if decision.start_ms < cursor:
                raise ValueError("framing decisions overlap while computing output coverage")
            if cursor < decision.start_ms:
                gaps.append(CoverageGap(edit.segment_id, cursor, decision.start_ms, "output"))
            cursor = max(cursor, decision.end_ms)
        if cursor < edit.out_end_ms:
            gaps.append(CoverageGap(edit.segment_id, cursor, edit.out_end_ms, "output"))
    return tuple(gaps)


def synthesize_source_base_coverage(
    *,
    content_edits: Iterable[ContentEdit],
    framing_decisions: Iterable[FramingDecision],
    observations: list[FrameObservation],
    quality: QualityMetrics,
) -> tuple[FramingDecision, ...]:
    """Fill every kept-content gap with an explicit no-zoom source-base crop.

    Source-base coverage is deliberately not a semantic zoom. It makes renderer
    behavior total and deterministic when no WHY-driven framing decision is active,
    including windows where gesture/prop transition masks make all semantic shot
    states unavailable. The source itself must remain displayable even when a
    composition target cannot be satisfied without inventing pixels.
    """
    content = tuple(content_edits)
    framing = tuple(framing_decisions)
    gaps = source_coverage_gaps(content, framing)
    generated: list[FramingDecision] = []

    for index, gap in enumerate(gaps):
        rows = _observations_for_range(observations, gap.start_ms, gap.end_ms)
        state = _classify_source_base(rows)
        crop = canonical_crop_for_window(
            observations=rows,
            metrics=quality,
            scale=1.0,
        )
        generated.append(
            FramingDecision(
                segment_id=(
                    f"coverage_{gap.content_segment_id}_{gap.start_ms:010d}_"
                    f"{gap.end_ms:010d}_{index:03d}"
                ),
                start_ms=gap.start_ms,
                end_ms=gap.end_ms,
                state=state,
                motion_intent=MotionIntent.STATIC,
                primitive=RenderPrimitive.HOLD,
                crop_start=crop,
                crop_end=crop,
                anchor_policy="source_base_explicit_coverage",
                time_basis="source",
                why={
                    "reason": "coverage_source_base",
                    "semantic_trigger": False,
                },
                desired={
                    "requested_state": None,
                    "selected_state": state,
                    "coverage": True,
                },
                can={
                    "source_base": True,
                    "scale": 1.0,
                    "reason": "no_active_semantic_framing",
                },
                when={
                    "reason": "coverage_gap",
                    "start_ms": gap.start_ms,
                    "end_ms": gap.end_ms,
                },
                derived={
                    "coverage_generated": True,
                    "motion_start_scale": 1.0,
                    "motion_end_scale": 1.0,
                    "motion_duration_ms": 0,
                },
                gates_passed=("coverage_explicit", "scale_floor"),
                speech_impact="none",
            )
        )

    combined = tuple(sorted(framing + tuple(generated), key=lambda item: (item.start_ms, item.segment_id)))
    if source_coverage_gaps(content, combined):
        raise AssertionError("coverage synthesis failed to cover kept content")
    return combined
