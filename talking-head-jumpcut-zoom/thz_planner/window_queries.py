from __future__ import annotations

from typing import Any

from .schema import FeasibleShotState, ShotState


def window_at(result: dict[str, Any], t_ms: int) -> dict[str, Any] | None:
    for window in result.get("windows", []):
        if int(window["start_ms"]) <= t_ms <= int(window["end_ms"]):
            return window
    return None


def state_in_window(window: dict[str, Any], state: ShotState) -> FeasibleShotState | None:
    for item in window.get("distinct_states", []):
        if item.state is state:
            return item
    return None


def state_is_feasible(result: dict[str, Any], state: ShotState, t_ms: int) -> bool:
    window = window_at(result, t_ms)
    return window is not None and state_in_window(window, state) is not None


def feasible_ranges(result: dict[str, Any], state: ShotState) -> list[tuple[int, int]]:
    """Merge adjacent planner buckets where a distinct state is available."""
    ranges: list[tuple[int, int]] = []
    for window in result.get("windows", []):
        if state_in_window(window, state) is None:
            continue
        start, end = int(window["start_ms"]), int(window["end_ms"])
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def choose_available_state(
    window: dict[str, Any],
    desired: ShotState,
) -> FeasibleShotState | None:
    """Deterministic degradation toward the closest semantic framing state."""
    states = {item.state: item for item in window.get("distinct_states", [])}
    if desired in states:
        return states[desired]
    preference = {
        ShotState.EMPHASIS: (ShotState.ARGUMENT, ShotState.CONTEXT),
        ShotState.ARGUMENT: (ShotState.CONTEXT, ShotState.EMPHASIS),
        ShotState.CONTEXT: (ShotState.ARGUMENT, ShotState.EMPHASIS),
    }
    for fallback in preference[desired]:
        if fallback in states:
            return states[fallback]
    return None
