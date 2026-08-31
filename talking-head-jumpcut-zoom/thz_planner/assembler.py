from __future__ import annotations

from typing import Any

from .framing import canonical_crop_pair
from .motion import MotionPlan, fit_motion_duration
from .schema import FramingDecision, FrameObservation, QualityMetrics, RenderPrimitive
from .window_queries import feasible_ranges


def _observations_for_range(
    observations: list[FrameObservation],
    start_ms: int,
    end_ms: int,
) -> list[FrameObservation]:
    selected = [o for o in observations if start_ms <= o.t_ms <= end_ms]
    if selected:
        return sorted(selected, key=lambda o: o.t_ms)
    if not observations:
        raise ValueError("observations required")
    nearest = min(observations, key=lambda o: (abs(o.t_ms - start_ms), o.t_ms))
    return [nearest]


def _contiguous_end(geometry_result: dict[str, Any], state, start_ms: int) -> int | None:
    for range_start, range_end in feasible_ranges(geometry_result, state):
        if range_start <= start_ms <= range_end:
            return range_end
    return None


def materialize_framing_decision(
    *,
    transition: dict[str, object],
    geometry_result: dict[str, Any],
    observations: list[FrameObservation],
    quality: QualityMetrics,
    segment_id: str,
    requested_end_ms: int,
) -> FramingDecision:
    """Convert a planned transition into renderer-facing canonical crop geometry.

    The segment is clipped to the contiguous temporal-feasibility range of the
    selected state. A ramp therefore cannot silently continue into a future gesture
    or prop block that made the state infeasible.
    """
    if transition.get("status") != "PLANNED":
        raise ValueError("transition must have status=PLANNED")

    selected_state = transition["selected_state"]
    when = transition["when"]
    motion: MotionPlan = transition["motion"]
    start_ms = int(when["ms"])
    if requested_end_ms < start_ms:
        raise ValueError("requested_end_ms must be >= transition boundary")

    feasible_end = _contiguous_end(geometry_result, selected_state.state, start_ms)
    if feasible_end is None:
        raise ValueError("selected state is not feasible at chosen boundary")
    end_ms = min(int(requested_end_ms), feasible_end)
    available_ms = max(0, end_ms - start_ms)
    fitted = fit_motion_duration(motion, available_ms)

    if fitted.primitive is RenderPrimitive.STEP:
        start_scale = end_scale = fitted.end_scale
        crop_observations = _observations_for_range(observations, start_ms, end_ms)
    else:
        start_scale = fitted.start_scale
        end_scale = fitted.end_scale
        ramp_end_ms = min(end_ms, start_ms + fitted.duration_ms) if fitted.duration_ms else start_ms
        crop_observations = _observations_for_range(observations, start_ms, ramp_end_ms)

    crop_start, crop_end = canonical_crop_pair(
        observations=crop_observations,
        metrics=quality,
        start_scale=start_scale,
        end_scale=end_scale,
    )

    pattern = transition.get("pattern")
    pattern_id = pattern.get("pattern_id") if isinstance(pattern, dict) else None
    limiting = tuple(selected_state.limiting_reasons)

    return FramingDecision(
        segment_id=segment_id,
        start_ms=start_ms,
        end_ms=end_ms,
        state=selected_state.state,
        motion_intent=fitted.intent,
        primitive=fitted.primitive,
        crop_start=crop_start,
        crop_end=crop_end,
        anchor_policy="tracked_face_segment_headroom",
        why=dict(transition.get("why") or {}),
        desired={
            "requested_state": transition.get("desired_state"),
            "selected_state": selected_state.state,
            "degraded": bool(transition.get("degraded", False)),
            "pattern_id": pattern_id,
        },
        can={
            "feasible_range": (start_ms, feasible_end),
            "selected_scale": selected_state.scale,
            "limiting_reasons": limiting,
        },
        when={k: v for k, v in when.items() if k != "source"},
        derived={
            "motion_start_scale": fitted.start_scale,
            "motion_end_scale": fitted.end_scale,
            "motion_duration_ms": fitted.duration_ms,
            "requested_end_ms": requested_end_ms,
            "clipped_to_feasibility": end_ms < requested_end_ms,
        },
        gates_passed=("temporal_feasibility", "composition_safe", "boundary_hard_masks"),
        speech_impact="none",
    )
