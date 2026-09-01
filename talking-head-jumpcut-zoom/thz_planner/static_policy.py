from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


STATIC_CAP_MS = {
    "calm": 6500,
    "neutral": 5000,
    "high": 4000,
}

SEMANTIC_PUSH_EXTENSION_MS = 3000  # provisional
SEMANTIC_MOTION_RATE_MIN = 0.0075   # 0.75%/s provisional


class VisualActivity(str, Enum):
    DISCRETE_EVENT = "discrete_event"
    SEMANTIC_PUSH = "semantic_push"
    AMBIENT_DRIFT = "ambient_drift"
    AI_DEPLASTIC_DRIFT = "ai_deplastic_drift"
    NO_OP = "no_op"
    STATIC = "static"


@dataclass(frozen=True)
class StaticStretchAssessment:
    pace: str
    elapsed_ms: int
    base_cap_ms: int
    effective_cap_ms: int
    resets_timer: bool
    motion_credit: bool
    status: str  # pass|starvation_required
    reason: str


@dataclass(frozen=True)
class StarvationStep:
    stage: str  # R1..R5 from the working v1.6.2 baseline
    action_id: str
    edl_reason: str


def assess_static_stretch(
    *,
    pace: str,
    elapsed_ms: int,
    activity: VisualActivity,
    verified_scale_rate_per_s: float = 0.0,
) -> StaticStretchAssessment:
    """Mechanical STATIC_STRETCH policy, independent from legacy R1-R5 actions.

    Valid discrete events reset the timer. Ambient and AI de-plastic drift never
    extend/reset it. A semantic push receives provisional +3s only when its verified
    rendered/planned scale rate is >=0.75%/s. No-op events have no effect.
    """
    if pace not in STATIC_CAP_MS:
        raise ValueError(f"unknown pace: {pace}")
    if elapsed_ms < 0:
        raise ValueError("elapsed_ms must be non-negative")

    base = STATIC_CAP_MS[pace]
    resets = activity is VisualActivity.DISCRETE_EVENT
    motion_credit = (
        activity is VisualActivity.SEMANTIC_PUSH
        and verified_scale_rate_per_s >= SEMANTIC_MOTION_RATE_MIN
    )
    effective = base + (SEMANTIC_PUSH_EXTENSION_MS if motion_credit else 0)

    if resets:
        return StaticStretchAssessment(
            pace, elapsed_ms, base, effective, True, False, "pass", "valid_discrete_event"
        )
    if elapsed_ms <= effective:
        reason = "semantic_motion_credit" if motion_credit else "within_static_cap"
        return StaticStretchAssessment(
            pace, elapsed_ms, base, effective, False, motion_credit, "pass", reason
        )
    return StaticStretchAssessment(
        pace,
        elapsed_ms,
        base,
        effective,
        False,
        motion_credit,
        "starvation_required",
        "static_cap_exceeded",
    )


def validate_starvation_ladder(steps: tuple[StarvationStep, ...]) -> None:
    """Validate migrated R1-R5 ordering without inventing missing baseline actions."""
    expected = ("R1", "R2", "R3", "R4", "R5")
    stages = tuple(step.stage for step in steps)
    if stages != expected:
        raise ValueError(f"starvation ladder must preserve {expected}, got {stages}")
    if len({step.action_id for step in steps}) != len(steps):
        raise ValueError("starvation action ids must be unique")
    if any(not step.edl_reason for step in steps):
        raise ValueError("every starvation step requires an EDL reason")
