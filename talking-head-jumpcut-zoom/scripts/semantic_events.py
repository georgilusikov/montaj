#!/usr/bin/env python3
"""
Build planner-ready semantic_events from dense output words plus agent/LLM semantic marks.

The agent owns WHY, while performance may only amplify an already semantic mark:
- which span matters;
- semantic importance;
- direction;
- optional performance_emphasis + evidence;
- optional motion hint / zoom duration type;
- concise reason.

Performance never creates a semantic event and never promotes semantic importance <0.40.
The bonus is deliberately small (max +0.08) so HOW can strengthen WHAT without
reintroducing gaze/timer-driven zoom generation.

This module deterministically owns timing:
- maps word indices to dense timeline milliseconds;
- generates nearby word-boundary candidates;
- validates ordering and schema;
- fails closed when a normal-length spoken clip has no semantic marks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "1.7.5-lite"
VALID_DIRECTIONS = {
    "build", "peak", "release", "neutral",
    "ratchet_1", "ratchet_2", "ratchet_3",
}
VALID_MOTION_HINTS = {"auto", "step", "slow_push"}
VALID_DURATION_TYPES = {"micro_punch", "beat", "argument_hold"}
DEFAULT_REQUIRE_AFTER_MS = 8000
DEFAULT_BOUNDARY_RADIUS_WORDS = 2
PERFORMANCE_BONUS_MAX = 0.08
PERFORMANCE_SEMANTIC_FLOOR = 0.40


def _validate_words(raw_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = sorted((dict(w) for w in raw_words), key=lambda w: int(w["start_ms"]))
    prev_end = -1
    for index, word in enumerate(words):
        start = int(word["start_ms"])
        end = int(word["end_ms"])
        if start < 0 or end < start:
            raise ValueError(f"invalid word timing at index {index}: {start}..{end}")
        if start < prev_end:
            raise ValueError(f"overlapping/out-of-order dense words at index {index}")
        prev_end = end
    return words


def _spoken_span_ms(words: list[dict[str, Any]]) -> int:
    if not words:
        return 0
    return int(words[-1]["end_ms"]) - int(words[0]["start_ms"])


def _candidate(
    words: list[dict[str, Any]],
    index: int,
    *,
    candidate_id: str,
    at_start: bool,
) -> dict[str, Any]:
    word = words[index]
    ms = int(word["start_ms"] if at_start else word["end_ms"])
    pause = False
    if at_start and index > 0:
        pause = int(word["start_ms"]) - int(words[index - 1]["end_ms"]) >= 120
    elif not at_start and index + 1 < len(words):
        pause = int(words[index + 1]["start_ms"]) - int(word["end_ms"]) >= 120
    return {
        "id": candidate_id,
        "ms": ms,
        "word_boundary": True,
        "pause": pause,
        "word_index": index,
        "boundary_side": "start" if at_start else "end",
    }


def _boundary_candidates(
    words: list[dict[str, Any]],
    start_word: int,
    *,
    radius_words: int,
) -> list[dict[str, Any]]:
    if not words:
        return []
    lo = max(0, start_word - radius_words)
    hi = min(len(words) - 1, start_word + radius_words)
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    order = list(range(start_word, hi + 1)) + list(range(start_word - 1, lo - 1, -1))
    for idx in order:
        for at_start in (True, False):
            c = _candidate(
                words,
                idx,
                candidate_id=f"w{idx}_{'s' if at_start else 'e'}",
                at_start=at_start,
            )
            if c["ms"] in seen:
                continue
            seen.add(c["ms"])
            result.append(c)
    result.sort(key=lambda c: (abs(int(c["ms"]) - int(words[start_word]["start_ms"])), int(c["ms"])))
    return result


def _performance_adjusted_importance(mark: dict[str, Any], semantic_importance: float, event_id: str) -> tuple[float, float, float, str]:
    performance = float(mark.get("performance_emphasis", 0.0) or 0.0)
    if not 0.0 <= performance <= 1.0:
        raise ValueError(f"{event_id}: performance_emphasis must be within 0..1")
    evidence = str(mark.get("performance_evidence") or "").strip()
    if performance > 0.0 and not evidence:
        raise ValueError(f"{event_id}: performance_evidence is required when performance_emphasis > 0")

    bonus = 0.0
    if semantic_importance >= PERFORMANCE_SEMANTIC_FLOOR:
        # Only the upper half of performance intensity matters. Max bonus +0.08.
        bonus = min(PERFORMANCE_BONUS_MAX, max(0.0, performance - 0.50) * 0.16)
    effective = min(1.0, semantic_importance + bonus)
    return effective, performance, bonus, evidence


def build_events(payload: dict[str, Any]) -> dict[str, Any]:
    words = _validate_words(list(payload.get("words") or []))
    marks = list(payload.get("semantic_marks") or [])
    config = dict(payload.get("config") or {})
    require_after_ms = int(config.get("require_semantics_after_ms", DEFAULT_REQUIRE_AFTER_MS))
    allow_no_semantics = bool(config.get("allow_no_semantic_events", False))
    radius_words = max(0, int(config.get("boundary_radius_words", DEFAULT_BOUNDARY_RADIUS_WORDS)))

    span_ms = _spoken_span_ms(words)
    if words and span_ms >= require_after_ms and not marks and not allow_no_semantics:
        raise ValueError(
            "semantic_marks is empty for a normal-length spoken clip; "
            "agent must produce semantic WHY before zoom planning"
        )

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, raw in enumerate(marks):
        mark = dict(raw)
        event_id = str(mark.get("id") or f"semantic_{index:03d}")
        if event_id in seen_ids:
            raise ValueError(f"duplicate semantic mark id: {event_id}")
        seen_ids.add(event_id)

        start_word = int(mark["start_word"])
        end_word = int(mark.get("end_word", start_word))
        if not (0 <= start_word < len(words)):
            raise ValueError(f"{event_id}: start_word out of range: {start_word}")
        if not (start_word <= end_word < len(words)):
            raise ValueError(f"{event_id}: end_word out of range: {end_word}")

        semantic_importance = float(mark.get("importance", 0.0))
        if not 0.0 <= semantic_importance <= 1.0:
            raise ValueError(f"{event_id}: importance must be within 0..1")
        importance, performance, performance_bonus, performance_evidence = _performance_adjusted_importance(
            mark, semantic_importance, event_id
        )

        direction = str(mark.get("direction") or "").strip().lower()
        if direction and direction not in VALID_DIRECTIONS:
            raise ValueError(f"{event_id}: invalid direction: {direction}")

        motion_hint = str(mark.get("motion_hint") or "auto").strip().lower()
        if motion_hint not in VALID_MOTION_HINTS:
            raise ValueError(f"{event_id}: invalid motion_hint: {motion_hint}")

        duration_type = str(mark.get("zoom_duration_type") or "").strip().lower()
        if duration_type and duration_type not in VALID_DURATION_TYPES:
            raise ValueError(f"{event_id}: invalid zoom_duration_type: {duration_type}")

        why = str(mark.get("why") or "").strip()
        if not why:
            raise ValueError(f"{event_id}: semantic mark requires non-empty why")

        event = {
            "id": event_id,
            "t_ms": int(words[start_word]["start_ms"]),
            "end_ms": int(words[end_word]["end_ms"]),
            "importance": importance,
            "semantic_importance": semantic_importance,
            "performance_emphasis": performance,
            "performance_bonus": round(performance_bonus, 4),
            "boundary_candidates": _boundary_candidates(words, start_word, radius_words=radius_words),
            "semantic_source": "agent_mark_v1.7.5",
            "semantic_span": {
                "start_word": start_word,
                "end_word": end_word,
                "text": " ".join(str(words[i].get("text", "")) for i in range(start_word, end_word + 1)).strip(),
            },
            "semantic_why": why,
        }
        if performance_evidence:
            event["performance_evidence"] = performance_evidence
        if direction:
            event["direction"] = direction
        if motion_hint != "auto":
            event["motion_hint"] = motion_hint
        if duration_type:
            event["zoom_duration_type"] = duration_type
        if "transition_ms" in mark:
            event["transition_ms"] = int(mark["transition_ms"])
        events.append(event)

    events.sort(key=lambda e: (int(e["t_ms"]), str(e["id"])))
    return {
        "version": VERSION,
        "word_count": len(words),
        "spoken_span_ms": span_ms,
        "semantic_event_count": len(events),
        "semantic_events": events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Montaj semantic events from dense words + agent semantic marks")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    result = build_events(payload)
    Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
