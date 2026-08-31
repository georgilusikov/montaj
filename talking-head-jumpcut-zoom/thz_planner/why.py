from __future__ import annotations

from .schema import ShotState

WHY_WEIGHTS = {
    "semantic_weight": 0.45,
    "salience": 0.25,
    "prosody": 0.20,
    "narrative": 0.10,
}

ARGUMENT_THRESHOLD = 0.45
EMPHASIS_THRESHOLD = 0.78


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def resolve_why(
    *,
    semantic_weight: float,
    salience: float = 0.0,
    prosody: float = 0.0,
    narrative: float = 0.0,
    act_reset: bool = False,
) -> dict[str, object]:
    """Pure semantic WHY. Gaze/pose/cadence must not enter this function."""
    components = {
        "semantic_weight": _unit(semantic_weight),
        "salience": _unit(salience),
        "prosody": _unit(prosody),
        "narrative": _unit(narrative),
    }
    score = round(sum(WHY_WEIGHTS[k] * components[k] for k in WHY_WEIGHTS), 6)

    if act_reset:
        desired = ShotState.CONTEXT
        reason = "act_reset"
    elif score >= EMPHASIS_THRESHOLD:
        desired = ShotState.EMPHASIS
        reason = "semantic_emphasis"
    elif score >= ARGUMENT_THRESHOLD:
        desired = ShotState.ARGUMENT
        reason = "semantic_argument"
    else:
        desired = ShotState.CONTEXT
        reason = "semantic_context"

    return {
        "desired_state": desired,
        "score": score,
        "reason": reason,
        "components": components,
        "provisional": True,
    }
