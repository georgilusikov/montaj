from __future__ import annotations

from typing import Any

from .decision import plan_transition_intent


def plan_transition_from_semantic_context(
    semantic_context: dict[str, object],
    **planner_kwargs: Any,
) -> dict[str, object]:
    """Narrow bridge from frozen semantic evidence to deterministic planner WHY inputs."""
    required = ("semantic_weight", "salience", "prosody", "narrative", "act_reset")
    missing = [key for key in required if key not in semantic_context]
    if missing:
        raise ValueError(f"semantic context missing keys: {missing}")

    return plan_transition_intent(
        semantic_weight=float(semantic_context["semantic_weight"]),
        salience=float(semantic_context["salience"]),
        prosody=float(semantic_context["prosody"]),
        narrative=float(semantic_context["narrative"]),
        act_reset=bool(semantic_context["act_reset"]),
        theme_tag=(
            str(semantic_context["theme_tag"])
            if semantic_context.get("theme_tag") is not None
            else None
        ),
        **planner_kwargs,
    )
