from __future__ import annotations

from typing import Any

from .motion import plan_motion
from .patterns import PatternSpec, active_pattern_candidate, select_pattern, shape_state_with_pattern
from .schema import ShotState
from .when_solver import BoundaryCandidate, solve_ai_when, solve_live_when
from .why import resolve_why
from .window_queries import choose_available_state, state_is_feasible, window_at


def plan_transition_intent(
    *,
    geometry_result: dict[str, Any],
    semantic_at_ms: int,
    current_state: ShotState,
    current_scale: float,
    semantic_weight: float,
    salience: float = 0.0,
    prosody: float = 0.0,
    narrative: float = 0.0,
    act_reset: bool = False,
    theme_tag: str | None = None,
    boundary_candidates: list[BoundaryCandidate],
    profile: str = "live",
    segment_start_ms: int = 0,
    history_penalty: dict[str, float] | None = None,
    pace: str = "neutral",
    active_pattern_id: str | None = None,
    active_pattern_started_ms: int | None = None,
) -> dict[str, object]:
    """Deterministic decision core through WHY/PATTERN/WHEN/MOTION.

    WHY owns semantic intensity. PATTERN is an optional state-sequence prior with a
    deterministic lifecycle and may only shape at or below the WHY ceiling.
    Boundary candidates are then hard-masked against temporal feasibility.
    """
    why = resolve_why(
        semantic_weight=semantic_weight,
        salience=salience,
        prosody=prosody,
        narrative=narrative,
        act_reset=act_reset,
    )
    window = window_at(geometry_result, semantic_at_ms)
    if window is None:
        return {"status": "NO_WINDOW", "why": why}

    semantic_desired_state = why["desired_state"]
    available_states = {item.state for item in window.get("distinct_states", [])}

    # An explicit act reset terminates the previous pattern run. CONTEXT WHY also
    # remains unshaped; a pattern must never manufacture activity from weak meaning.
    if act_reset:
        active_pattern_id = None
        active_pattern_started_ms = None

    pattern = None
    continuing_active = False
    if semantic_desired_state is not ShotState.CONTEXT:
        pattern = active_pattern_candidate(
            active_pattern_id,
            theme_tag=theme_tag,
            available_states=available_states,
            semantic_fit=float(why["score"]),
            prosody_fit=prosody,
            history_penalty=history_penalty,
        )
        continuing_active = pattern is not None
        if pattern is None:
            pattern = select_pattern(
                theme_tag=theme_tag,
                available_states=available_states,
                semantic_fit=float(why["score"]),
                prosody_fit=prosody,
                history_penalty=history_penalty,
            )

    pattern_id = pattern.get("pattern_id") if isinstance(pattern, dict) else None
    if continuing_active and active_pattern_started_ms is not None:
        pattern_started_ms = int(active_pattern_started_ms)
    elif pattern is not None:
        pattern_started_ms = semantic_at_ms
    else:
        pattern_started_ms = None
    pattern_elapsed_ms = (
        max(0, semantic_at_ms - pattern_started_ms)
        if pattern_started_ms is not None
        else 0
    )
    metadata = pattern.get("metadata") if isinstance(pattern, dict) else None
    pattern_expired = (
        isinstance(metadata, PatternSpec)
        and pattern_elapsed_ms > metadata.max_duration_ms
    )

    pattern_target_state, pattern_shaped = shape_state_with_pattern(
        pattern,
        semantic_desired_state=semantic_desired_state,
        current_state=current_state,
        pattern_elapsed_ms=pattern_elapsed_ms,
    )

    selected_state = choose_available_state(window, pattern_target_state)
    if selected_state is None:
        return {
            "status": "NO_FEASIBLE_STATE",
            "why": why,
            "desired_state": semantic_desired_state,
            "pattern_target_state": pattern_target_state,
            "pattern_shaped": pattern_shaped,
            "pattern": pattern,
            "pattern_id": pattern_id,
            "pattern_started_ms": pattern_started_ms,
            "pattern_elapsed_ms": pattern_elapsed_ms,
            "pattern_expired": pattern_expired,
        }

    temporally_safe = [
        candidate
        for candidate in boundary_candidates
        if state_is_feasible(geometry_result, selected_state.state, candidate.ms)
    ]

    if profile == "live":
        when = solve_live_when(temporally_safe)
    elif profile == "ai_avatar":
        when = solve_ai_when(temporally_safe, segment_start_ms=segment_start_ms)
    else:
        raise ValueError(f"unknown profile: {profile}")

    if when is None:
        return {
            "status": "NO_SAFE_BOUNDARY",
            "why": why,
            "desired_state": semantic_desired_state,
            "pattern_target_state": pattern_target_state,
            "pattern_shaped": pattern_shaped,
            "selected_state": selected_state,
            "pattern": pattern,
            "pattern_id": pattern_id,
            "pattern_started_ms": pattern_started_ms,
            "pattern_elapsed_ms": pattern_elapsed_ms,
            "pattern_expired": pattern_expired,
        }

    motion = plan_motion(
        current_state=current_state,
        desired_state=selected_state.state,
        current_scale=current_scale,
        target_scale=selected_state.scale,
        semantic_weight=semantic_weight,
        pace=pace,
    )

    return {
        "status": "PLANNED",
        "why": why,
        "desired_state": semantic_desired_state,
        "pattern_target_state": pattern_target_state,
        "pattern_shaped": pattern_shaped,
        "selected_state": selected_state,
        "degraded": selected_state.state is not pattern_target_state,
        "pattern": pattern,
        "pattern_id": pattern_id,
        "pattern_started_ms": pattern_started_ms,
        "pattern_elapsed_ms": pattern_elapsed_ms,
        "pattern_expired": pattern_expired,
        "when": when,
        "motion": motion,
    }
