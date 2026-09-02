#!/usr/bin/env python3
"""v1.7.6 semantic adapter over the unchanged v1.7.5 semantic_events module."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import semantic_events as core

VERSION = "1.7.6-lite"
SEMANTIC_ZOOM_FLOOR = 0.40


def _mark_id(mark: dict[str, Any], index: int) -> str:
    return str(mark.get("id") or f"semantic_{index:03d}")


def build_events(payload: dict[str, Any]) -> dict[str, Any]:
    marks = [dict(mark) for mark in (payload.get("semantic_marks") or [])]
    config = dict(payload.get("config") or {})
    allow_legacy = bool(config.get("allow_legacy_semantic_defaults", False))

    # Validate the v1.7.6 contract before falling through to the stable v1.7.5 core.
    for index, mark in enumerate(marks):
        event_id = _mark_id(mark, index)
        raw_importance = float(mark.get("importance", 0.0) or 0.0)
        direction = str(mark.get("direction") or "").strip().lower()
        requires_zoom_contract = raw_importance >= SEMANTIC_ZOOM_FLOOR and direction != "release"
        if requires_zoom_contract and not allow_legacy:
            if not str(mark.get("block_id") or "").strip():
                raise ValueError(f"{event_id}: block_id is required for v1.7.6 semantic framing")
            if "accent_word" not in mark:
                raise ValueError(f"{event_id}: accent_word is required for v1.7.6 semantic framing")

    base = core.build_events({**payload, "semantic_marks": marks})
    words = core._validate_words(list(payload.get("words") or []))
    radius_words = max(
        0,
        int(config.get("boundary_radius_words", core.DEFAULT_BOUNDARY_RADIUS_WORDS)),
    )
    marks_by_id = {_mark_id(mark, i): mark for i, mark in enumerate(marks)}

    for event in base.get("semantic_events", []):
        event_id = str(event.get("id") or "")
        mark = marks_by_id.get(event_id, {})
        span = dict(event.get("semantic_span") or {})
        start_word = int(span.get("start_word", mark.get("start_word", 0)))
        end_word = int(span.get("end_word", mark.get("end_word", start_word)))

        block_id = str(mark.get("block_id") or event_id).strip() or event_id
        accent_word = int(mark.get("accent_word", start_word))
        if not (start_word <= accent_word <= end_word):
            raise ValueError(
                f"{event_id}: accent_word must be within semantic span "
                f"{start_word}..{end_word}, got {accent_word}"
            )

        semantic_start_ms = int(event["t_ms"])
        semantic_end_ms = int(event["end_ms"])
        event["block_id"] = block_id
        event["accent_word"] = accent_word
        event["accent_ms"] = int(words[accent_word]["start_ms"])
        event["semantic_start_ms"] = semantic_start_ms
        event["semantic_duration_ms"] = max(0, semantic_end_ms - semantic_start_ms)
        event["boundary_candidates"] = core._boundary_candidates(
            words,
            accent_word,
            radius_words=radius_words,
        )
        event["semantic_contract"] = "legacy_fallback" if (
            "block_id" not in mark or "accent_word" not in mark
        ) else "v1.7.6"

    base["version"] = VERSION
    base["config"] = dict(config)
    base["config"]["allow_legacy_semantic_defaults"] = allow_legacy
    return base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build v1.7.6 block/accent semantic events")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    result = build_events(payload)
    Path(args.output_json).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
