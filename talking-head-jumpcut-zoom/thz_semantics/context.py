from __future__ import annotations

from .prosody import BreathInterval, ProsodyPeak
from .schema import ActAnnotation, SalienceHit


def _contains(start_ms: int, end_ms: int, t_ms: int) -> bool:
    return start_ms <= t_ms <= end_ms


def semantic_context_at(
    t_ms: int,
    *,
    salience_hits: tuple[SalienceHit, ...] = (),
    prosody_peaks: tuple[ProsodyPeak, ...] = (),
    acts: tuple[ActAnnotation, ...] = (),
    act_reset_window_ms: int = 250,
) -> dict[str, object]:
    """Convert frozen semantic evidence at one time into planner WHY inputs."""
    local_hits = [h for h in salience_hits if _contains(h.start_ms, h.end_ms, t_ms)]
    local_peaks = [p for p in prosody_peaks if _contains(p.start_ms, p.end_ms, t_ms)]
    containing_acts = [a for a in acts if _contains(a.start_ms, a.end_ms, t_ms)]
    act = containing_acts[0] if containing_acts else None

    salience = max((h.weight for h in local_hits), default=0.0)
    # z-score 3.0 maps to 1.0; threshold 1.5 maps to 0.5.
    prosody = min(1.0, max((p.strength for p in local_peaks), default=0.0) / 3.0)
    semantic_weight = act.semantic_weight if act else salience

    theme_tag = None
    if act and act.theme_probabilities:
        theme_tag = sorted(act.theme_probabilities, key=lambda x: (-x[1], x[0]))[0][0]

    ordered_acts = sorted(acts, key=lambda a: (a.start_ms, a.act_id))
    is_first = bool(act and ordered_acts and act.act_id == ordered_acts[0].act_id)
    act_reset = bool(
        act
        and not is_first
        and 0 <= t_ms - act.start_ms <= act_reset_window_ms
    )

    return {
        "semantic_weight": round(float(semantic_weight), 6),
        "salience": round(float(salience), 6),
        "prosody": round(float(prosody), 6),
        "narrative": 0.0,
        "theme_tag": theme_tag,
        "act_reset": act_reset,
        "evidence_ids": tuple(
            sorted([h.hit_id for h in local_hits] + [p.peak_id for p in local_peaks])
        ),
        "act_id": act.act_id if act else None,
    }


def distance_to_breath_ms(t_ms: int, breaths: tuple[BreathInterval, ...]) -> int | None:
    """Signed distance to nearest breath interval edge; 0 if inside a breath."""
    if not breaths:
        return None
    distances: list[int] = []
    for breath in breaths:
        if breath.start_ms <= t_ms <= breath.end_ms:
            return 0
        if t_ms < breath.start_ms:
            distances.append(t_ms - breath.start_ms)
        else:
            distances.append(t_ms - breath.end_ms)
    return min(distances, key=lambda x: (abs(x), x))
