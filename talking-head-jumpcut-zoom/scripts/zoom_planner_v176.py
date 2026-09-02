#!/usr/bin/env python3
"""v1.7.6 Reels cadence adapter over the unchanged v1.7.5 zoom_planner."""
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

REELS_HOME_SCALE = 1.00
ZOOM_LEVELS = {"Z1": 1.03, "Z2": 1.06, "Z3": 1.09, "Z4": 1.13}
REELS_ABSOLUTE_CAP = ZOOM_LEVELS["Z4"]
CADENCE_MAX_LEVEL = "Z2"

Z2_IMPORTANCE = 0.55
Z3_IMPORTANCE = 0.72
Z4_IMPORTANCE = 0.85

MIN_CHANGE_GAP_MS = 2000
PREFERRED_CHANGE_GAP_MS = 3500
MAX_CHANGE_GAP_MS = 5000

LEVEL_FALLBACKS = {
    "Z1": (1.03, 1.02),
    "Z2": (1.06, 1.05, 1.04),
    "Z3": (1.09, 1.08, 1.07),
    "Z4": (1.13, 1.12, 1.11, 1.10),
}


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


def _crop_scale(crop: list[int] | tuple[int, int, int, int], width: int, height: int) -> float:
    _, _, crop_w, crop_h = (int(v) for v in crop)
    return min(width / max(crop_w, 1), height / max(crop_h, 1))


def _is_home_crop(crop: list[int] | tuple[int, int, int, int], width: int, height: int) -> bool:
    return [int(v) for v in crop] == [0, 0, width, height]


def _semantic_level(decision: dict[str, Any]) -> str | None:
    state = str(decision.get("state", "CONTEXT")).upper()
    direction = str(decision.get("direction") or "").lower()
    importance = float(decision.get("importance", decision.get("semantic_importance", 0.0)) or 0.0)

    if state == "CONTEXT" or direction == "release":
        return None
    if direction == "ratchet_3" or direction == "peak" or state == "EMPHASIS":
        return "Z4"
    if direction == "ratchet_2":
        return "Z3"
    if direction == "ratchet_1" or bool(decision.get("soft_build")) or direction == "build":
        return "Z2"
    if importance >= Z4_IMPORTANCE:
        return "Z4"
    if importance >= Z3_IMPORTANCE:
        return "Z3"
    if importance >= Z2_IMPORTANCE:
        return "Z2"
    return "Z1"


def _safe_crop_at_scale(
    observations: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    width: int,
    height: int,
    window_ms: int,
    target_scale: float,
    quality_cap: float,
    global_anchor: tuple[float, float, float],
    candidate_scales: tuple[float, ...] | None = None,
) -> tuple[float, list[int], float | None] | None:
    if target_scale <= 1.000001:
        return 1.0, [0, 0, width, height], None

    rows = core._segment_samples(observations, start_ms, end_ms, window_ms)
    requested = min(float(target_scale), float(quality_cap), REELS_ABSOLUTE_CAP)
    candidates = candidate_scales or (requested,)

    for scale in candidates:
        scale = min(float(scale), requested)
        if scale <= 1.000001:
            continue
        crop = core._crop_for_scale_with_anchor(
            rows,
            width,
            height,
            scale,
            global_anchor=global_anchor,
        )
        safe, _ = core._crop_safe(rows, crop, width, height, scale)
        if not safe:
            continue
        headroom_ratio = core._min_headroom_ratio(rows, crop, height)
        return (
            round(scale, 4),
            list(crop),
            round(headroom_ratio, 4) if headroom_ratio is not None else None,
        )
    return None


def _retarget_semantic_scales(result: dict[str, Any], prepared: dict[str, Any]) -> None:
    width = int(result["source"]["width"])
    height = int(result["source"]["height"])
    observations = sorted(list(prepared.get("observations") or []), key=lambda o: int(o["t_ms"]))
    if not observations:
        return

    config = dict(result.get("config") or {})
    window_ms = int(config.get("window_ms", 1200))
    quality_cap = float(prepared.get("source", {}).get("quality_cap", REELS_ABSOLUTE_CAP))
    global_anchor = core._get_global_anchor(observations)
    event_by_id = {str(event.get("id")): event for event in (prepared.get("semantic_events") or [])}

    for decision in result.get("decisions", []):
        if decision.get("status") != "PLANNED":
            continue
        event = event_by_id.get(str(decision.get("event_id") or ""), {})
        semantic_context = dict(decision)
        if "importance" in event:
            semantic_context["importance"] = event["importance"]
            decision["importance"] = event["importance"]
        if "semantic_importance" in event:
            semantic_context["semantic_importance"] = event["semantic_importance"]
            decision["semantic_importance"] = event["semantic_importance"]
        level = _semantic_level(semantic_context)
        if level is None:
            continue

        target_scale = ZOOM_LEVELS[level]
        start_ms = int(decision.get("start_ms", decision.get("event_ms", 0)))
        end_ms = int(decision.get("end_ms", start_ms))
        safe = _safe_crop_at_scale(
            observations,
            start_ms=start_ms,
            end_ms=end_ms,
            width=width,
            height=height,
            window_ms=window_ms,
            target_scale=target_scale,
            quality_cap=quality_cap,
            global_anchor=global_anchor,
            candidate_scales=LEVEL_FALLBACKS[level],
        )
        if safe is None:
            continue

        actual_scale, crop, headroom_ratio = safe
        decision["crop_end"] = crop
        decision["scale"] = actual_scale
        decision["headroom_ratio"] = headroom_ratio
        decision["zoom_level"] = level
        decision["reels_role"] = level
        decision["reels_target_scale"] = target_scale
        decision["reels_scale_limited"] = actual_scale + 0.005 < target_scale
        decision["state_cap"] = target_scale


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
        next_crop = list(next_decision.get("crop_end") or [])
        if previous_crop and previous_crop == next_crop:
            next_decision["motion"] = "hold"
            next_decision["transition_end_ms"] = int(next_decision.get("start_ms", 0))
            next_decision["why"] = "same_block_hold"

    if suppressed:
        result["returns"] = [
            ret for ret in returns
            if str(ret.get("parent_event_id") or "") not in suppressed
        ]
    return len(suppressed)


def _visible_fixed_changes(
    *,
    duration_ms: int,
    content_cuts_ms: list[int],
    decisions: list[dict[str, Any]],
    returns: list[dict[str, Any]],
) -> list[int]:
    changes = {0, max(0, int(duration_ms))}
    changes.update(max(0, min(duration_ms, int(t))) for t in content_cuts_ms)
    for decision in decisions:
        if (
            decision.get("status") == "PLANNED"
            and str(decision.get("motion", "hold")) != "hold"
            and decision.get("crop_start") != decision.get("crop_end")
        ):
            changes.add(max(0, min(duration_ms, int(decision.get("start_ms", 0)))))
    for ret in returns:
        if ret.get("crop_start") != ret.get("crop_end"):
            changes.add(max(0, min(duration_ms, int(ret.get("start_ms", 0)))))
    return sorted(changes)


def _reels_cadence_requests(
    *,
    duration_ms: int,
    content_cuts_ms: list[int],
    decisions: list[dict[str, Any]],
    returns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known = _visible_fixed_changes(
        duration_ms=duration_ms,
        content_cuts_ms=content_cuts_ms,
        decisions=decisions,
        returns=returns,
    )
    requests: list[dict[str, Any]] = []

    for left, right in zip(known, known[1:]):
        cursor = left
        while right - cursor > MAX_CHANGE_GAP_MS:
            earliest = cursor + MIN_CHANGE_GAP_MS
            latest = min(cursor + MAX_CHANGE_GAP_MS, right - MIN_CHANGE_GAP_MS)
            if latest < earliest:
                break
            desired = max(earliest, min(cursor + PREFERRED_CHANGE_GAP_MS, latest))
            requests.append({
                "at_ms": int(desired),
                "window_start_ms": int(earliest),
                "window_end_ms": int(latest),
                "preferred_action": "cadence_low_level_refresh",
                "fallback_action": "hold_if_no_safe_refresh",
                "semantic_trigger": False,
                "gap_start_ms": int(cursor),
                "gap_end_ms": int(right),
            })
            cursor = int(desired)
    return requests


def _visual_candidate_ok(row: dict[str, Any]) -> bool:
    if any(bool(row.get(k, False)) for k in (
        "blink", "blur", "hard_block", "eyes_closed", "long_eye_closure",
        "pose_unsafe", "strong_head_turn",
    )):
        return False
    ear = row.get("ear")
    if ear is not None and float(ear) < 0.20:
        return False
    mar = row.get("mar")
    if mar is not None and float(mar) > 0.45:
        return False
    laplacian_var = row.get("laplacian_var")
    if laplacian_var is not None and float(laplacian_var) < 60.0:
        return False
    flow_speed = row.get("flow_speed_px") or row.get("motion_speed_px")
    if flow_speed is not None and float(flow_speed) > 2.0:
        return False
    return True


def _choose_cadence_time(observations: list[dict[str, Any]], request: dict[str, Any]) -> int | None:
    lo = int(request["window_start_ms"])
    hi = int(request["window_end_ms"])
    desired = int(request["at_ms"])
    candidates = [row for row in observations if lo <= int(row["t_ms"]) <= hi and _visual_candidate_ok(row)]
    if not candidates:
        return None
    candidates.sort(key=lambda row: (
        0 if row.get("head_return") else 1,
        abs(int(row["t_ms"]) - desired),
        int(row["t_ms"]),
    ))
    return int(candidates[0]["t_ms"])


def _fixed_timeline_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for decision in result.get("decisions", []):
        if decision.get("status") == "PLANNED":
            items.append({
                "start_ms": int(decision.get("start_ms", 0)),
                "priority": 1,
                "crop_end": list(decision.get("crop_end") or []),
            })
    for ret in result.get("returns", []):
        items.append({
            "start_ms": int(ret.get("start_ms", 0)),
            "priority": 0,
            "crop_end": list(ret.get("crop_end") or []),
        })
    items.sort(key=lambda item: (item["start_ms"], item["priority"]))
    return items


def _next_cadence_level(current_scale: float) -> str:
    if current_scale <= 1.005:
        return "Z1"
    if current_scale <= ZOOM_LEVELS["Z1"] + 0.01:
        return "Z2"
    return "Z1"


def _materialize_cadence(
    result: dict[str, Any],
    prepared: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    width = int(result["source"]["width"])
    height = int(result["source"]["height"])
    observations = sorted(list(prepared.get("observations") or []), key=lambda o: int(o["t_ms"]))
    if not observations:
        return [], requests

    config = dict(result.get("config") or {})
    window_ms = int(config.get("window_ms", 1200))
    quality_cap = float(prepared.get("source", {}).get("quality_cap", REELS_ABSOLUTE_CAP))
    global_anchor = core._get_global_anchor(observations)
    fixed = _fixed_timeline_items(result)

    current_crop = [0, 0, width, height]
    fixed_index = 0
    cadence_decisions: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for index, request in enumerate(sorted(requests, key=lambda r: int(r["at_ms"]))):
        desired_ms = int(request["at_ms"])
        while fixed_index < len(fixed) and fixed[fixed_index]["start_ms"] <= desired_ms:
            crop_end = fixed[fixed_index]["crop_end"]
            if crop_end:
                current_crop = list(crop_end)
            fixed_index += 1

        current_scale = _crop_scale(current_crop, width, height)
        if current_scale > ZOOM_LEVELS[CADENCE_MAX_LEVEL] + 0.01:
            unresolved.append(dict(request, reason="semantic_framing_has_priority"))
            continue

        chosen_ms = _choose_cadence_time(observations, request)
        if chosen_ms is None:
            unresolved.append(dict(request, reason="no_safe_visual_boundary"))
            continue

        level = _next_cadence_level(current_scale)
        safe = _safe_crop_at_scale(
            observations,
            start_ms=chosen_ms,
            end_ms=chosen_ms + window_ms,
            width=width,
            height=height,
            window_ms=window_ms,
            target_scale=ZOOM_LEVELS[level],
            quality_cap=quality_cap,
            global_anchor=global_anchor,
            candidate_scales=LEVEL_FALLBACKS[level],
        )
        if safe is None:
            unresolved.append(dict(request, reason="no_safe_low_level_crop"))
            continue

        target_scale, target_crop, headroom_ratio = safe
        cadence_decisions.append({
            "event_id": f"cadence_{level.lower()}_{index:03d}",
            "event_ms": desired_ms,
            "start_ms": chosen_ms,
            "end_ms": chosen_ms,
            "transition_end_ms": chosen_ms,
            "status": "PLANNED",
            "state": "SOFT",
            "base_desired_state": "SOFT",
            "desired_state": "SOFT",
            "direction": "cadence_refresh",
            "motion": "step",
            "motion_hint": "step",
            "crop_start": list(current_crop),
            "crop_end": list(target_crop),
            "scale": round(float(target_scale), 4),
            "state_cap": ZOOM_LEVELS[level],
            "why": "cadence_low_level_refresh",
            "semantic_trigger": False,
            "cadence_refresh": True,
            "zoom_level": level,
            "reels_role": f"CADENCE_{level}",
            "headroom_ratio": headroom_ratio,
        })
        current_crop = list(target_crop)

    return cadence_decisions, unresolved


def _normalize_timeline_crop_starts(result: dict[str, Any]) -> None:
    width = int(result["source"]["width"])
    height = int(result["source"]["height"])
    current_crop = [0, 0, width, height]

    items: list[tuple[int, int, dict[str, Any]]] = []
    for decision in result.get("decisions", []):
        if decision.get("status") == "PLANNED":
            items.append((int(decision.get("start_ms", 0)), 1, decision))
    for ret in result.get("returns", []):
        items.append((int(ret.get("start_ms", 0)), 0, ret))
    items.sort(key=lambda item: (item[0], item[1]))

    for _, _, item in items:
        item["crop_start"] = list(current_crop)
        if str(item.get("motion", "step")) == "hold":
            item["crop_end"] = list(current_crop)
        current_crop = list(item.get("crop_end") or current_crop)


def _rhythm_summary(result: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    duration_ms = int(result.get("source", {}).get("duration_ms") or 0)
    event_by_id = {str(event.get("id")): event for event in events}

    decision_changes = [
        decision for decision in result.get("decisions", [])
        if decision.get("status") == "PLANNED"
        and str(decision.get("motion", "hold")) != "hold"
        and decision.get("crop_start") != decision.get("crop_end")
    ]
    return_changes = [ret for ret in result.get("returns", []) if ret.get("crop_start") != ret.get("crop_end")]
    starts = sorted(
        [int(item.get("start_ms", 0)) for item in decision_changes]
        + [int(item.get("start_ms", 0)) for item in return_changes]
    )
    gaps = [right - left for left, right in zip(starts, starts[1:])]

    semantic_visible = [d for d in decision_changes if not bool(d.get("cadence_refresh"))]
    cadence_visible = [d for d in decision_changes if bool(d.get("cadence_refresh"))]

    episodes = 0
    previous_block: str | None = None
    previous_start: int | None = None
    for decision in sorted(semantic_visible, key=lambda item: int(item.get("start_ms", 0))):
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

    level_counts = {level: 0 for level in ZOOM_LEVELS}
    for decision in decision_changes:
        level = str(decision.get("zoom_level") or "")
        if level in level_counts:
            level_counts[level] += 1

    per_min = 0.0 if duration_ms <= 0 else len(starts) * 60000.0 / duration_ms
    return {
        "visible_framing_change_count": len(starts),
        "semantic_change_count": len(semantic_visible),
        "cadence_low_level_change_count": len(cadence_visible),
        "semantic_episode_count": episodes,
        "zoom_level_counts": level_counts,
        "framing_changes_per_min": round(per_min, 2),
        "median_gap_between_framing_changes_ms": int(median(gaps)) if gaps else None,
        "cadence_min_gap_ms": MIN_CHANGE_GAP_MS,
        "cadence_preferred_gap_ms": PREFERRED_CHANGE_GAP_MS,
        "cadence_max_gap_ms": MAX_CHANGE_GAP_MS,
    }


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    prepared, events = _prepare_payload(payload)

    original_zoom_duration = core._zoom_duration
    core._zoom_duration = _semantic_zoom_duration
    try:
        result = core.plan(prepared)
    finally:
        core._zoom_duration = original_zoom_duration

    _retarget_semantic_scales(result, prepared)

    continuation_ms = max(
        0,
        int((payload.get("config") or {}).get("same_block_continuation_ms", SAME_BLOCK_CONTINUATION_MS)),
    )
    suppressed = _suppress_same_block_returns(result, events, continuation_ms)

    duration_ms = int(result.get("source", {}).get("duration_ms") or 0)
    content_cuts_ms = [int(v) for v in (prepared.get("content_cuts_ms") or [])]
    cadence_requests = _reels_cadence_requests(
        duration_ms=duration_ms,
        content_cuts_ms=content_cuts_ms,
        decisions=list(result.get("decisions") or []),
        returns=list(result.get("returns") or []),
    )
    cadence_decisions, unresolved = _materialize_cadence(result, prepared, cadence_requests)
    result.setdefault("decisions", []).extend(cadence_decisions)
    _normalize_timeline_crop_starts(result)

    result["cadence_requests"] = unresolved
    result["cadence_low_level_changes"] = len(cadence_decisions)
    result["version"] = VERSION
    result.setdefault("config", {})["same_block_continuation_ms"] = continuation_ms
    result["config"]["reels_cadence"] = {
        "min_change_gap_ms": MIN_CHANGE_GAP_MS,
        "preferred_change_gap_ms": PREFERRED_CHANGE_GAP_MS,
        "max_change_gap_ms": MAX_CHANGE_GAP_MS,
    }
    result["config"]["reels_scales"] = {"HOME": REELS_HOME_SCALE, **ZOOM_LEVELS}
    result["config"]["semantic_importance_thresholds"] = {
        "Z2": Z2_IMPORTANCE,
        "Z3": Z3_IMPORTANCE,
        "Z4": Z4_IMPORTANCE,
    }
    result["config"]["cadence_max_level"] = CADENCE_MAX_LEVEL
    result["config"]["absolute_zoom_cap"] = min(
        REELS_ABSOLUTE_CAP,
        float(prepared.get("source", {}).get("quality_cap", REELS_ABSOLUTE_CAP)),
    )
    result["config"]["state_caps"] = {
        "CONTEXT": REELS_HOME_SCALE,
        "SOFT": ZOOM_LEVELS["Z2"],
        "ARGUMENT": ZOOM_LEVELS["Z3"],
        "EMPHASIS": ZOOM_LEVELS["Z4"],
    }
    result["same_block_returns_suppressed"] = suppressed
    result["rhythm_summary"] = _rhythm_summary(result, events)

    visual_times = {0, duration_ms}
    visual_times.update(content_cuts_ms)
    for decision in result.get("decisions", []):
        if (
            decision.get("status") == "PLANNED"
            and str(decision.get("motion", "hold")) != "hold"
            and decision.get("crop_start") != decision.get("crop_end")
        ):
            visual_times.add(int(decision.get("start_ms", 0)))
    for ret in result.get("returns", []):
        if ret.get("crop_start") != ret.get("crop_end"):
            visual_times.add(int(ret.get("start_ms", 0)))
    result["visual_change_times_ms"] = sorted(t for t in visual_times if 0 <= t <= duration_ms)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan v1.7.6 Reels four-level semantic + cadence framing")
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
