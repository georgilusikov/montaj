from __future__ import annotations

import math

from .schema import FeasibilityInterval, FeasibleShotState, ShotState

STATE_ORDER = {
    ShotState.CONTEXT: 0,
    ShotState.ARGUMENT: 1,
    ShotState.EMPHASIS: 2,
}

SCALE_STEP_MIN = {
    "calm": 0.04,
    "neutral": 0.06,
    "high": 0.06,
}


def composition_distance(a: FeasibilityInterval, b: FeasibilityInterval, *, pace: str) -> float:
    """Provisional normalized perceptual distance between two framing states.

    A value >=1.0 is considered distinguishable. We include scale, rendered
    face-size and rendered face-center movement rather than relying on scale alone.
    """
    if pace not in SCALE_STEP_MIN:
        raise ValueError(f"unknown pace: {pace}")
    scale_threshold = SCALE_STEP_MIN[pace]
    scale_rel = abs(b.actual_scale / max(a.actual_scale, 1e-9) - 1.0)
    scale_component = scale_rel / scale_threshold

    face_component = abs(b.metrics.face_ratio_p50 - a.metrics.face_ratio_p50) / 0.04
    center_delta = math.hypot(
        b.metrics.face_center_x_p50 - a.metrics.face_center_x_p50,
        b.metrics.face_center_y_p50 - a.metrics.face_center_y_p50,
    )
    center_component = center_delta / 0.04

    return round(
        0.50 * scale_component + 0.35 * face_component + 0.15 * center_component,
        6,
    )


def derive_distinct_states(
    intervals: list[FeasibilityInterval],
    *,
    pace: str,
) -> list[FeasibleShotState]:
    candidates = sorted(
        (item for item in intervals if item.feasible),
        key=lambda x: STATE_ORDER[x.state],
    )
    if not candidates:
        return []

    chosen: list[FeasibilityInterval] = [candidates[0]]
    distances: list[float | None] = [None]

    for candidate in candidates[1:]:
        distance = composition_distance(chosen[-1], candidate, pace=pace)
        if distance >= 1.0:
            chosen.append(candidate)
            distances.append(distance)
            continue

        # If ARGUMENT is perceptually redundant but EMPHASIS is the endpoint,
        # prefer the endpoint. This yields two real states instead of three fake ones.
        if candidate.state is ShotState.EMPHASIS and chosen[-1].state is ShotState.ARGUMENT:
            previous = chosen[-2] if len(chosen) >= 2 else None
            replacement_distance = (
                composition_distance(previous, candidate, pace=pace)
                if previous is not None
                else None
            )
            if previous is None or (replacement_distance is not None and replacement_distance >= 1.0):
                chosen[-1] = candidate
                distances[-1] = replacement_distance

    result: list[FeasibleShotState] = []
    for item, distance in zip(chosen, distances):
        result.append(
            FeasibleShotState(
                state=item.state,
                scale=item.actual_scale,
                face_ratio_p50=item.metrics.face_ratio_p50,
                face_center_x_p50=item.metrics.face_center_x_p50,
                face_center_y_p50=item.metrics.face_center_y_p50,
                composition_distance_from_previous=distance,
                limiting_reasons=item.metrics.limiting_reasons,
            )
        )
    return result
