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

# A pattern is a shaping prior, not a mandatory template. Unthemed/weak evidence
# leaves WHY unshaped. This threshold is provisional and calibration-owned.
PATTERN_ACTIVATION_THRESHOLD = 0.35

STATE_LEVEL = {
    ShotState.CONTEXT: 0,
    ShotState.ARGUMENT: 1,
    ShotState.EMPHASIS: 2,
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


def select_pattern(
    *,
    theme_tag: str | None,
    available_states: set[ShotState],
    semantic_fit: float,
    prosody_fit: float,
    history_penalty: dict[str, float] | None = None,
    activation_threshold: float = PATTERN_ACTIVATION_THRESHOLD,
) -> dict[str, object] | None:
    # Unknown/absent theme evidence must not silently impose a pattern.
    if theme_tag not in THEME_PRIORS:
        return None
    candidates = pattern_candidates(
        theme_tag=theme_tag,
        available_states=available_states,
        semantic_fit=semantic_fit,
        prosody_fit=prosody_fit,
        history_penalty=history_penalty,
    )
    if not candidates or float(candidates[0]["score"]) < activation_threshold:
        return None
    return candidates[0]


def active_pattern_candidate(
    pattern_id: str | None,
    *,
    theme_tag: str | None,
    available_states: set[ShotState],
    semantic_fit: float,
    prosody_fit: float,
    history_penalty: dict[str, float] | None = None,
) -> dict[str, object] | None:
    """Resolve an already-active pattern under the current state feasibility.

    An active run may continue even if a later semantic event has no theme tag, but
    it is dropped immediately when its required state set can no longer degrade to a
    valid candidate.
    """
    if not pattern_id:
        return None
    for candidate in pattern_candidates(
        theme_tag=theme_tag,
        available_states=available_states,
        semantic_fit=semantic_fit,
        prosody_fit=prosody_fit,
        history_penalty=history_penalty,
    ):
        if candidate["pattern_id"] == pattern_id:
            return candidate
    return None


def shape_state_with_pattern(
    pattern: dict[str, object] | None,
    *,
    semantic_desired_state: ShotState,
    current_state: ShotState,
    pattern_elapsed_ms: int = 0,
) -> tuple[ShotState, bool]:
    """Use pattern sequence as a semantic ceiling-preserving shaping prior.

    WHY owns the maximum allowed semantic intensity. A pattern may stage a strong
    EMPHASIS request through ARGUMENT first, or perform its declared reset, but it
    can never elevate a CONTEXT/ARGUMENT WHY request into a stronger state.
    """
    if pattern_elapsed_ms < 0:
        raise ValueError("pattern_elapsed_ms must be non-negative")
    if pattern is None or semantic_desired_state is ShotState.CONTEXT:
        return semantic_desired_state, False

    usable = tuple(pattern.get("usable_states") or ())
    metadata = pattern.get("metadata")
    if not usable or not isinstance(metadata, PatternSpec):
        return semantic_desired_state, False

    # Expiry is deterministic. Patterns that owe a reset return toward the first
    # usable state; non-reset patterns simply stop shaping and hand control to WHY.
    if pattern_elapsed_ms > metadata.max_duration_ms:
        if metadata.required_reset:
            candidate = usable[0]
        else:
            return semantic_desired_state, False
    elif current_state not in usable:
        return semantic_desired_state, False
    else:
        index = usable.index(current_state)
        if index + 1 < len(usable):
            candidate = usable[index + 1]
        elif metadata.required_reset:
            candidate = usable[0]
        else:
            candidate = usable[-1]

    ceiling = STATE_LEVEL[semantic_desired_state]
    if STATE_LEVEL[candidate] > ceiling:
        allowed = [state for state in usable if STATE_LEVEL[state] <= ceiling]
        candidate = max(allowed, key=lambda state: STATE_LEVEL[state]) if allowed else semantic_desired_state

    return candidate, candidate is not semantic_desired_state
