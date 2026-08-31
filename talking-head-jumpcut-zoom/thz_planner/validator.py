from __future__ import annotations

from typing import Any

from .coverage import output_coverage_gaps
from .framing import derived_scale
from .global_policy import home_return_report, pattern_reset_report, state_balance_report
from .schema import FramingDecision, QualityMetrics, RenderPrimitive
from .timeline import ContentEdit, validate_content_edits


def _validate_crop(crop, quality: QualityMetrics) -> None:
    if crop.w <= 0 or crop.h <= 0:
        raise ValueError("crop dimensions must be positive")
    if any(value % 2 for value in (crop.x, crop.y, crop.w, crop.h)):
        raise ValueError("canonical crop coordinates/dimensions must be even")
    if crop.x < 0 or crop.y < 0:
        raise ValueError("crop origin must be non-negative")
    if crop.x + crop.w > quality.width or crop.y + crop.h > quality.height:
        raise ValueError("crop exceeds source bounds")
    if derived_scale(quality, crop) < 1.0:
        raise ValueError("derived scale below 1.00 is forbidden")


def validate_framing_decision(decision: FramingDecision, quality: QualityMetrics) -> None:
    if decision.start_ms < 0 or decision.end_ms < decision.start_ms:
        raise ValueError("invalid framing timestamps")
    if decision.time_basis not in {"source", "output"}:
        raise ValueError("unknown framing time basis")
    _validate_crop(decision.crop_start, quality)
    _validate_crop(decision.crop_end, quality)

    motion_duration = int(decision.derived.get("motion_duration_ms", 0))
    if motion_duration < 0 or motion_duration > decision.end_ms - decision.start_ms:
        raise ValueError("motion duration exceeds framing segment")
    if decision.primitive is RenderPrimitive.HOLD and decision.crop_start != decision.crop_end:
        raise ValueError("hold primitive must have identical start/end crop")


def validate_manifest_pre_render(
    manifest: dict[str, Any],
    *,
    quality: QualityMetrics,
    require_full_coverage: bool = True,
    pace: str | None = None,
) -> dict[str, object]:
    content: tuple[ContentEdit, ...] = validate_content_edits(manifest.get("content_edits", ()))
    framing: tuple[FramingDecision, ...] = tuple(manifest.get("framing_decisions", ()))
    for decision in framing:
        validate_framing_decision(decision, quality)
        if decision.time_basis != "output":
            raise ValueError("renderer manifest framing must use output time basis")

    gaps = output_coverage_gaps(manifest)
    if require_full_coverage and gaps:
        compact = ",".join(
            f"{gap.content_segment_id}:{gap.start_ms}-{gap.end_ms}"
            for gap in gaps[:5]
        )
        raise ValueError(f"renderer framing coverage gaps: {compact}")

    pattern_violations = pattern_reset_report(framing)
    if pattern_violations:
        first = pattern_violations[0]
        raise ValueError(
            "pattern reset contract violated: "
            f"{first.segment_id}:{first.pattern_id}:{first.reason}"
        )

    home_violations = home_return_report(framing)
    if home_violations:
        first = home_violations[0]
        raise ValueError(
            "HOME_RETURN global safety max exceeded: "
            f"{first.start_ms}-{first.end_ms} ({first.duration_ms}ms)"
        )

    balance = state_balance_report(framing, pace=pace) if pace is not None else None
    return {
        "status": "PASS",
        "content_edit_count": len(content),
        "framing_decision_count": len(framing),
        "coverage_gap_count": len(gaps),
        "framing_coverage": 1.0 if not gaps else 0.0,
        "pattern_reset_violation_count": len(pattern_violations),
        "home_return_violation_count": len(home_violations),
        "state_balance": balance,
    }
