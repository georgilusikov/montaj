#!/usr/bin/env python3
"""v1.7.6 zoom adapter over the unchanged v1.7.5 zoom_planner module."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from statistics import median
from typing import Any

import zoom_planner as core

VERSION = "1.7.6-lite"
SAME_BLOCK_CONTINUATION_MS = 1200


def _semantic_zoom_duration(event: dict[str, Any], start_ms: int) -> tuple[str, int]:
    explicit = str(event.get("zoom_duration_type") or "").strip().lower()
    if "semantic_duration_ms" in event:
        raw_ms = max(0, int(event.get("semantic_duration_ms") or 0))
    else:
        semantic_start_ms = int(event.get("semantic_start_ms", event.get("t_ms", start_ms)))
        raw_ms = max(0, int(event.get("end_ms", semantic_start_ms)) - semantic_start_ms)

    if explicit in core.ZOOM_DURATION_BANDS_MS:
        kind = explicit
    elif raw_ms and raw_ms < 1500:
        kind = "micro_punch"
    elif raw_ms and raw_ms < 2500:
        kind = "beat"
    elif raw_ms:
        kind = "argument_hold"
    else:
        kind = "beat"

    lo, hi, default = core.ZOOM_DURATION_BANDS_MS[kind]
    duration = default if raw_ms <= 0 else int(core._clamp(raw_ms, lo, hi))
    return kind, duration


def _prepare_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prepared = copy.deepcopy(payload)
    events = list(prepared.get("semantic_events") or [])
    for event in events:
        if "semantic_start_ms" not in event:
            event["semantic_start_ms"] = int(event.get("t_ms", 0))
        if "semantic_duration_ms" not in event:
            event["semantic_duration_ms"] = max(
                0,
                int(event.get("end_ms", event["semantic_start_ms"])) - int(event["semantic_start_ms"]),
            )
        if event.get("accent_ms") is not None:
            event["t_ms"] = int(event["accent_ms"])
    events.sort(key=lambda event: (int(event.get("t_ms", 0)), str(event.get("id", ""))))
    prepared["semantic_events"] = events
    return prepared, events


def _planned_by_event(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(decision.get("event_id")): decision
        for decision in decisions
        if decision.get("status") == "PLANNED"
    }


def _suppress_same_block_returns(
    result: dict[str, Any],
    events: list[dict[str, Any]],
    continuation_ms: int,
) -> int:
    decisions = list(result.get("decisions") or [])
    returns = list(result.get("returns") or [])
    planned = _planned_by_event(decisions)
    index_by_id = {str(event.get("id")): i for i, event in enumerate(events)}
    event_by_id = {str(event.get("id")): event for event in events}
    suppressed: set[str] = set()

    for ret in returns:
        parent_id = str(ret.get("parent_event_id") or "")
        parent_event = event_by_id.get(parent_id)
        parent_decision = planned.get(parent_id)
        parent_index = index_by_id.get(parent_id)
        if parent_event is None or parent_decision is None or parent_index is None:
            continue
        if parent_index + 1 >= len(events):
            continue

        next_event = events[parent_index + 1]
        next_decision = planned.get(str(next_event.get("id") or ""))
        if next_decision is None or str(next_decision.get("state")) == "CONTEXT":
            continue
        if str(next_event.get("direction") or "").strip().lower() == "release":
            continue

        parent_block = str(parent_event.get("block_id") or "").strip()
        next_block = str(next_event.get("block_id") or "").strip()
        if not parent_block or parent_block != next_block:
            continue

        return_ms = int(ret.get("start_ms", ret.get("end_ms", 0)))
        next_start_ms = int(next_decision.get("start_ms", next_event.get("t_ms", 0)))
        if next_start_ms - return_ms > continuation_ms:
            continue

        suppressed.add(parent_id)
        parent_decision["auto_return"] = False
        parent_decision["continued_by_next"] = True
        parent_decision["continuation_reason"] = "same_block"
        previous_crop = list(parent_decision.get("crop_end") or [])
        next_decision["crop_start"] = previous_crop
        if previous_crop == list(next_decision.get("crop_end") or []):
            next_decision["motion"] = "hold"
            next_decision["transition_end_ms"] = int(next_decision.get("start_ms", 0))
            next_decision["why"] = "same_block_hold"

    if suppressed:
        result["returns"] = [
            ret for ret in returns
            if str(ret.get("parent_event_id") or "") not in suppressed
        ]
    return len(suppressed)


def _rhythm_summary(result: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    duration_ms = int(result.get("source", {}).get("duration_ms") or 0)
    event_by_id = {str(event.get("id")): event for event in events}
    visible = [
        decision for decision in result.get("decisions", [])
        if decision.get("status") == "PLANNED"
        and str(decision.get("state")) != "CONTEXT"
        and str(decision.get("motion", "hold")) != "hold"
        and decision.get("crop_start") != decision.get("crop_end")
    ]
    starts = sorted(int(decision.get("start_ms", 0)) for decision in visible)
    gaps = [right - left for left, right in zip(starts, starts[1:])]

    episodes = 0
    previous_block: str | None = None
    previous_start: int | None = None
    for decision in sorted(visible, key=lambda item: int(item.get("start_ms", 0))):
        event = event_by_id.get(str(decision.get("event_id")), {})
        block = str(event.get("block_id") or decision.get("event_id") or "")
        start = int(decision.get("start_ms", 0))
        same_episode = (
            previous_block is not None
            and block == previous_block
            and previous_start is not None
            and start - previous_start <= SAME_BLOCK_CONTINUATION_MS + 2500
        )
        if not same_episode:
            episodes += 1
        previous_block = block
        previous_start = start

    per_min = 0.0 if duration_ms <= 0 else len(visible) * 60000.0 / duration_ms
    return {
        "visible_zoom_change_count": len(visible),
        "semantic_episode_count": episodes,
        "zoom_changes_per_min": round(per_min, 2),
        "median_gap_between_zoom_changes_ms": int(median(gaps)) if gaps else None,
        "observational_ceiling_changes_per_min": round(60000 / 7000, 2),
        "ceiling_is_diagnostic_not_quota": True,
    }


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    prepared, events = _prepare_payload(payload)
    original_zoom_duration = core._zoom_duration
    core._zoom_duration = _semantic_zoom_duration
    try:
        result = core.plan(prepared)
    finally:
        core._zoom_duration = original_zoom_duration

    continuation_ms = max(
        0,
        int((payload.get("config") or {}).get("same_block_continuation_ms", SAME_BLOCK_CONTINUATION_MS)),
    )
    suppressed = _suppress_same_block_returns(result, events, continuation_ms)

    source_duration_ms = int(result.get("source", {}).get("duration_ms") or 0)
    intensity = str(result.get("config", {}).get("intensity", "moderate"))
    known, requests = core._cadence_requests(
        duration_ms=source_duration_ms,
        content_cuts_ms=[int(v) for v in (prepared.get("content_cuts_ms") or [])],
        decisions=list(result.get("decisions") or []),
        returns=list(result.get("returns") or []),
        intensity=intensity,
    )
    result["visual_change_times_ms"] = known
    result["cadence_requests"] = requests
    result["version"] = VERSION
    result.setdefault("config", {})["same_block_continuation_ms"] = continuation_ms
    result["same_block_returns_suppressed"] = suppressed
    result["rhythm_summary"] = _rhythm_summary(result, events)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan v1.7.6 semantic zoom episodes")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    result = plan(payload)
    Path(args.output_json).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
