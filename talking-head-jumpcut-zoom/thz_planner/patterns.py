from __future__ import annotations

from dataclasses import dataclass

from .schema import ShotState, stable_candidate_sort


@dataclass(frozen=True)
class PatternSpec:
    pattern_id: str
    ideal_states: tuple[ShotState, ...]
    min_state_count: int
    max_duration_ms: int = 12000
    required_reset: bool = True
    allowed_terminal_states: tuple[ShotState, ...] = (ShotState.CONTEXT, ShotState.ARGUMENT)


PATTERNS = {
    "ladder": PatternSpec("ladder", (ShotState.CONTEXT, ShotState.ARGUMENT, ShotState.EMPHASIS), 2),
    "wisdom_arc": PatternSpec("wisdom_arc", (ShotState.CONTEXT, ShotState.ARGUMENT, ShotState.EMPHASIS), 2),
    "punch": PatternSpec("punch", (ShotState.CONTEXT, ShotState.EMPHASIS), 2, required_reset=False),
    "wave": PatternSpec("wave", (ShotState.CONTEXT, ShotState.ARGUMENT, ShotState.EMPHASIS), 2),
    "sawtooth": PatternSpec("sawtooth", (ShotState.CONTEXT, ShotState.ARGUMENT, ShotState.EMPHASIS), 2),
    "plateau": PatternSpec("plateau", (ShotState.CONTEXT, ShotState.ARGUMENT), 1, required_reset=False),
    "ladder_down": PatternSpec("ladder_down", (ShotState.EMPHASIS, ShotState.ARGUMENT, ShotState.CONTEXT), 2, required_reset=False),
}

THEME_PRIORS = {
    "warning": {"ladder": 0.80, "punch": 0.50, "wave": 0.20},
    "secret": {"ladder": 0.70, "plateau": 0.55, "punch": 0.35},
    "insight": {"punch": 0.85, "ladder": 0.55, "wave": 0.30},
    "story": {"wisdom_arc": 0.80, "wave": 0.50, "punch": 0.20},
    "myth_bust": {"sawtooth": 0.75, "wave": 0.65, "punch": 0.45},
    "instruction": {"plateau": 0.80, "ladder": 0.45, "wave": 0.25},
    "outro": {"ladder_down": 0.80, "wisdom_arc": 0.30},
}

PATTERN_WEIGHTS = {
    "theme": 0.45,
    "semantic": 0.25,
    "prosody": 0.15,
    "history": 0.15,
}


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def pattern_candidates(
    *,
    theme_tag: str | None,
    available_states: set[ShotState],
    semantic_fit: float,
    prosody_fit: float,
    history_penalty: dict[str, float] | None = None,
) -> list[dict[str, object]]:
    """Hard-mask infeasible patterns, then score remaining candidates deterministically."""
    history_penalty = history_penalty or {}
    priors = THEME_PRIORS.get(theme_tag or "", {})
    candidates: list[dict[str, object]] = []

    for pattern_id, spec in PATTERNS.items():
        usable = tuple(state for state in spec.ideal_states if state in available_states)
        if len(set(usable)) < spec.min_state_count:
            continue

        theme_prior = _unit(priors.get(pattern_id, 0.10))
        hist = _unit(history_penalty.get(pattern_id, 0.0))
        score = (
            PATTERN_WEIGHTS["theme"] * theme_prior
            + PATTERN_WEIGHTS["semantic"] * _unit(semantic_fit)
            + PATTERN_WEIGHTS["prosody"] * _unit(prosody_fit)
            - PATTERN_WEIGHTS["history"] * hist
        )
        candidates.append(
            {
                "id": pattern_id,
                "pattern_id": pattern_id,
                "score": round(score, 6),
                "semantic_fit": _unit(semantic_fit),
                "theme_prior": theme_prior,
                "prosody_fit": _unit(prosody_fit),
                "history_penalty": hist,
                "usable_states": usable,
                "degraded": tuple(spec.ideal_states) != usable,
                "metadata": spec,
                "ms": 0,
            }
        )

    return stable_candidate_sort(candidates)


def select_pattern(**kwargs) -> dict[str, object] | None:
    candidates = pattern_candidates(**kwargs)
    return candidates[0] if candidates else None
