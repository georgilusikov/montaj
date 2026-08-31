from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIDeplasticDrift:
    start_scale: float = 1.00
    end_scale: float = 1.02
    continuous: bool = True
    counts_as_semantic_motion: bool = False
    counts_as_static_reset: bool = False
    counts_as_static_extension: bool = False


def default_ai_deplastic_drift() -> AIDeplasticDrift:
    """Legacy AI anti-plastic drift, deliberately outside semantic framing credit."""
    return AIDeplasticDrift()


def validate_ai_deplastic_drift(drift: AIDeplasticDrift) -> None:
    if drift.start_scale < 1.0 or drift.end_scale < drift.start_scale:
        raise ValueError("invalid AI de-plastic drift scale range")
    if drift.end_scale > 1.02 + 1e-9:
        raise ValueError("AI de-plastic drift must remain within legacy 1.00→1.02 cap")
    if drift.counts_as_semantic_motion or drift.counts_as_static_reset or drift.counts_as_static_extension:
        raise ValueError("AI de-plastic drift must not earn semantic/static motion credit")
