from __future__ import annotations

from typing import Any

from .motion import plan_motion
from .patterns import select_pattern, shape_state_with_pattern
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
) -> dict[str, object]:
    """P0C deterministic decision core through WHY/PATTERN/WHEN/MOTION.

    WHY owns semantic intensity. PATTERN may shape that target downward into a
    sequence but cannot increase it. Boundary candidates are then hard-masked
    against temporal feasibility of the shaped selected state.
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
    pattern = select_pattern(
        theme_tag=theme_tag,
        available_states=available_states,
        semantic_fit=float(why["score"]),
        prosody_fit=prosody,
        history_penalty=history_penalty,
    )
    pattern_target_state, pattern_shaped = shape_state_with_pattern(
        pattern,
        semantic_desired_state=semantic_desired_state,
        current_state=current_state,
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
        "when": when,
        "motion": motion,
    }
