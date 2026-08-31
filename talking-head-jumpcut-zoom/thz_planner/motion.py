from __future__ import annotations

from dataclasses import dataclass

from .schema import MotionIntent, RenderPrimitive, ShotState
from .shot_states import SCALE_STEP_MIN

SEMANTIC_PUSH_REL_CAP = 1.06
SEMANTIC_PUSH_RATE_MAX = 0.015
AMBIENT_DRIFT_REL_CAP = 1.02
AMBIENT_DRIFT_RATE_MAX = 0.005


@dataclass(frozen=True)
class MotionPlan:
    intent: MotionIntent
    primitive: RenderPrimitive
    start_scale: float
    end_scale: float
    max_rate_per_s: float | None
    provisional: bool = True


def _delta_rel(a: float, b: float) -> float:
    return abs(b / max(a, 1e-9) - 1.0)


def plan_motion(
    *,
    current_state: ShotState,
    desired_state: ShotState,
    current_scale: float,
    target_scale: float,
    semantic_weight: float,
    pace: str,
) -> MotionPlan:
    if pace not in SCALE_STEP_MIN:
        raise ValueError(f"unknown pace: {pace}")
    if current_scale < 1.0 or target_scale < 1.0:
        raise ValueError("scale < 1.00 is not supported")

    if current_state is desired_state and _delta_rel(current_scale, target_scale) < 1e-6:
        return MotionPlan(MotionIntent.STATIC, RenderPrimitive.HOLD, current_scale, current_scale, None)

    delta = _delta_rel(current_scale, target_scale)
    if delta >= SCALE_STEP_MIN[pace]:
        intent = MotionIntent.SEMANTIC_PUSH if target_scale > current_scale else MotionIntent.SEMANTIC_PULL
        return MotionPlan(intent, RenderPrimitive.STEP, current_scale, target_scale, None)

    # Small semantic changes are not fake discrete plans. They become a ramp only
    # when the meaning is strong enough and pace allows it.
    if target_scale > current_scale and semantic_weight >= 0.80 and pace != "high":
        end_scale = min(target_scale, current_scale * SEMANTIC_PUSH_REL_CAP)
        return MotionPlan(
            MotionIntent.SEMANTIC_PUSH,
            RenderPrimitive.LINEAR_RAMP,
            current_scale,
            round(end_scale, 6),
            SEMANTIC_PUSH_RATE_MAX,
        )

    if target_scale < current_scale and semantic_weight >= 0.65:
        return MotionPlan(
            MotionIntent.SEMANTIC_PULL,
            RenderPrimitive.LINEAR_RAMP,
            current_scale,
            target_scale,
            0.02,
        )

    return MotionPlan(MotionIntent.STATIC, RenderPrimitive.HOLD, current_scale, current_scale, None)


def ambient_drift(current_scale: float) -> MotionPlan:
    if current_scale < 1.0:
        raise ValueError("scale < 1.00 is not supported")
    return MotionPlan(
        MotionIntent.AMBIENT_DRIFT,
        RenderPrimitive.LINEAR_RAMP,
        current_scale,
        round(current_scale * AMBIENT_DRIFT_REL_CAP, 6),
        AMBIENT_DRIFT_RATE_MAX,
    )
