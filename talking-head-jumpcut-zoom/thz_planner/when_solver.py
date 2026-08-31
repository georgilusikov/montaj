from __future__ import annotations

from dataclasses import dataclass

from .schema import stable_candidate_sort

BREATH_GUARD_MS = 120


@dataclass(frozen=True)
class BoundaryCandidate:
    candidate_id: str
    ms: int
    semantic_fit: float = 0.0
    word_boundary: bool = False
    pause_score: float = 0.0
    head_return: bool = False
    breath_distance_ms: int | None = None
    blink_block: bool = False
    blur_block: bool = False
    prop_block: bool = False
    eye_closure_block: bool = False
    artifact_peak: bool = False
    phoneme_boundary: bool = False


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _hard_safe(candidate: BoundaryCandidate) -> bool:
    return not (
        candidate.blink_block
        or candidate.blur_block
        or candidate.prop_block
        or candidate.eye_closure_block
    )


def solve_live_when(candidates: list[BoundaryCandidate]) -> dict[str, object] | None:
    """Select a live boundary after WHY has already requested a state change."""
    scored: list[dict[str, object]] = []
    for candidate in candidates:
        if not _hard_safe(candidate):
            continue
        breath_guard = (
            candidate.breath_distance_ms is not None
            and abs(candidate.breath_distance_ms) <= BREATH_GUARD_MS
        )
        score = (
            0.45 * _unit(candidate.semantic_fit)
            + 0.20 * float(candidate.word_boundary)
            + 0.15 * _unit(candidate.pause_score)
            + 0.20 * float(candidate.head_return)
            - 0.15 * float(breath_guard)
        )
        scored.append(
            {
                "id": candidate.candidate_id,
                "ms": candidate.ms,
                "score": round(score, 6),
                "semantic_fit": _unit(candidate.semantic_fit),
                "head_return_bonus": candidate.head_return,
                "breath_guard": breath_guard,
                "hard_safe": True,
                "source": candidate,
            }
        )
    ordered = stable_candidate_sort(scored)
    return ordered[0] if ordered else None


def solve_ai_when(
    candidates: list[BoundaryCandidate],
    *,
    segment_start_ms: int,
    cadence_min_ms: int = 2000,
    cadence_max_ms: int = 4000,
) -> dict[str, object] | None:
    """AI-avatar: artifact peak and forced cadence are hard candidate constraints."""
    scored: list[dict[str, object]] = []
    for candidate in candidates:
        if not _hard_safe(candidate) or not candidate.artifact_peak:
            continue
        elapsed = candidate.ms - segment_start_ms
        if elapsed < cadence_min_ms or elapsed > cadence_max_ms:
            continue
        score = (
            0.55 * _unit(candidate.semantic_fit)
            + 0.30 * float(candidate.phoneme_boundary)
            + 0.15 * _unit(candidate.pause_score)
        )
        scored.append(
            {
                "id": candidate.candidate_id,
                "ms": candidate.ms,
                "score": round(score, 6),
                "semantic_fit": _unit(candidate.semantic_fit),
                "artifact_peak": True,
                "phoneme_boundary": candidate.phoneme_boundary,
                "cadence_elapsed_ms": elapsed,
                "hard_safe": True,
                "source": candidate,
            }
        )
    ordered = stable_candidate_sort(scored)
    return ordered[0] if ordered else None
