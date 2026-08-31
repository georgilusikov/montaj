from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticsProvenance:
    semantics_version: str
    input_hash: str
    model_id: str | None = None
    model_revision: str | None = None
    temperature: float | None = None
    prompt_version: str | None = None


@dataclass(frozen=True)
class SalienceHit:
    hit_id: str
    start_ms: int
    end_ms: int
    kind: str
    weight: float
    evidence: str
    provenance: str = "deterministic_probe"


@dataclass(frozen=True)
class ActAnnotation:
    act_id: str
    start_ms: int
    end_ms: int
    semantic_weight: float
    theme_probabilities: tuple[tuple[str, float], ...]
    provenance: str = "llm"


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def validate_acts(acts: tuple[ActAnnotation, ...]) -> tuple[ActAnnotation, ...]:
    ordered = tuple(sorted(acts, key=lambda x: (x.start_ms, x.act_id)))
    previous_end = -1
    seen: set[str] = set()
    for act in ordered:
        if not act.act_id or act.act_id in seen:
            raise ValueError("act ids must be non-empty and unique")
        seen.add(act.act_id)
        if act.start_ms < 0 or act.end_ms <= act.start_ms:
            raise ValueError("invalid act range")
        if act.start_ms < previous_end:
            raise ValueError("acts must not overlap")
        if not 0.0 <= act.semantic_weight <= 1.0:
            raise ValueError("semantic_weight must be in 0..1")
        total = 0.0
        themes: set[str] = set()
        for theme, probability in act.theme_probabilities:
            if not theme or theme in themes:
                raise ValueError("theme ids must be non-empty and unique per act")
            themes.add(theme)
            if not 0.0 <= probability <= 1.0:
                raise ValueError("theme probability must be in 0..1")
            total += probability
        if act.theme_probabilities and total > 1.000001:
            raise ValueError("theme probabilities must sum to <= 1")
        previous_end = act.end_ms
    return ordered
