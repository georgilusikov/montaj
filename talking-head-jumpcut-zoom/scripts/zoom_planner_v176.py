#!/usr/bin/env python3
"""v1.7.6 Reels adapter over the unchanged v1.7.5 zoom planner."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from statistics import median
from typing import Any

import zoom_planner as core

VERSION = "1.7.6-lite"
HOME = 1.00
ZOOM_LEVELS = {"Z1": 1.03, "Z2": 1.06, "Z3": 1.09, "Z4": 1.13}
LEVEL_FALLBACKS = {
    "Z1": (1.03, 1.02),
    "Z2": (1.06, 1.05, 1.04),
    "Z3": (1.09, 1.08, 1.07),
    "Z4": (1.13, 1.12, 1.11, 1.10),
}
ABS_CAP = 1.13
CADENCE_MAX_LEVEL = "Z2"
Z2_IMPORTANCE, Z3_IMPORTANCE, Z4_RAW_IMPORTANCE = 0.55, 0.72, 0.90

# Calmer Reels rhythm after real-video review.
MIN_GAP_MS, PREFERRED_GAP_MS, MAX_GAP_MS = 3000, 4500, 6000
SAME_BLOCK_MS = 1200

# Slow push should feel like an intentional camera move, not constant drift.
SLOW_PUSH_TARGET_MS = 2000
MIN_PUSH_MS = 1200
MIN_SETTLE_MS = 500
LEVEL_RANK = {"Z1": 1, "Z2": 2, "Z3": 3, "Z4": 4}


def _duration(event: dict[str, Any], start_ms: int) -> tuple[str, int]:
    explicit = str(event.get("zoom_duration_type") or "").lower()
    raw = int(event.get("semantic_duration_ms") or 0)
    if raw <= 0:
        semantic_start = int(event.get("semantic_start_ms", event.get("t_ms", start_ms)))
        raw = max(0, int(event.get("end_ms", semantic_start)) - semantic_start)
    if explicit in core.ZOOM_DURATION_BANDS_MS:
        kind = explicit
    elif raw and raw < 1500:
        kind = "micro_punch"
    elif raw and raw < 2500:
        kind = "beat"
    elif raw:
        kind = "argument_hold"
    else:
        kind = "beat"
    lo, hi, default = core.ZOOM_DURATION_BANDS_MS[kind]
    semantic_visual = default if raw <= 0 else int(core._clamp(raw, lo, hi))
    # Semantic span still owns meaning; visual dwell is deliberately calmer.
    return kind, max(MIN_GAP_MS, semantic_visual)


def _prepare(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    out = copy.deepcopy(payload)
    events = list(out.get("semantic_events") or [])
    for event in events:
        event.setdefault("semantic_start_ms", int(event.get("t_ms", 0)))
        event.setdefault(
            "semantic_duration_ms",
            max(
                0,
                int(event.get("end_ms", event["semantic_start_ms"]))
                - int(event["semantic_start_ms"]),
            ),
        )
        if event.get("accent_ms") is not None:
            event["t_ms"] = int(event["accent_ms"])
    events.sort(key=lambda e: (int(e.get("t_ms", 0)), str(e.get("id", ""))))
    out["semantic_events"] = events
    return out, events


def _scale(crop: list[int] | tuple[int, int, int, int], w: int, h: int) -> float:
    return min(w / max(int(crop[2]), 1), h / max(int(crop[3]), 1))


def _semantic_level(d: dict[str, Any]) -> str | None:
    if str(d.get("state", "CONTEXT")).upper() == "CONTEXT":
        return None
    direction = str(d.get("direction") or "").lower()
    if direction == "release":
        return None
    effective = float(d.get("importance", d.get("semantic_importance", 0.0)) or 0.0)
    raw = float(d.get("semantic_importance", effective) or 0.0)
    if direction in {"peak", "ratchet_3"}:
        return "Z4"
    if direction == "ratchet_2":
        return "Z3"
    if direction == "ratchet_1" or bool(d.get("soft_build")) or direction == "build":
        return "Z2"
    if raw >= Z4_RAW_IMPORTANCE:
        return "Z4"
    if effective >= Z3_IMPORTANCE:
        return "Z3"
    if effective >= Z2_IMPORTANCE:
        return "Z2"
    return "Z1"


def _safe_crop(
    observations: list[dict[str, Any]],
    start: int,
    end: int,
    w: int,
    h: int,
    window: int,
    target: float,
    quality_cap: float,
    anchor: tuple[float, float, float],
    candidates: tuple[float, ...],
) -> tuple[float, list[int], float | None] | None:
    rows = core._segment_samples(observations, start, end, window)
    requested = min(target, quality_cap, ABS_CAP)
    for candidate in candidates:
        scale = min(float(candidate), requested)
        crop = core._crop_for_scale_with_anchor(
            rows, w, h, scale, global_anchor=anchor
        )
        safe, _ = core._crop_safe(rows, crop, w, h, scale)
        if safe:
            headroom = core._min_headroom_ratio(rows, crop, h)
            return (
                round(scale, 4),
                list(crop),
                round(headroom, 4) if headroom is not None else None,
            )
    return None


def _retarget(result: dict[str, Any], prepared: dict[str, Any]) -> None:
    w, h = int(result["source"]["width"]), int(result["source"]["height"])
    obs = sorted(
        list(prepared.get("observations") or []), key=lambda o: int(o["t_ms"])
    )
    if not obs:
        return
    window = int((result.get("config") or {}).get("window_ms", 1200))
    quality = float(prepared.get("source", {}).get("quality_cap", ABS_CAP))
    anchor = core._get_global_anchor(obs)
    by_id = {
        str(e.get("id")): e for e in prepared.get("semantic_events", [])
    }
    for d in result.get("decisions", []):
        if d.get("status") != "PLANNED":
            continue
        e = by_id.get(str(d.get("event_id") or ""), {})
        for key in ("importance", "semantic_importance", "semantic_duration_ms"):
            if key in e:
                d[key] = e[key]
        level = _semantic_level(d)
        if not level:
            continue
        safe = _safe_crop(
            obs,
            int(d.get("start_ms", 0)),
            int(d.get("end_ms", d.get("start_ms", 0))),
            w,
            h,
            window,
            ZOOM_LEVELS[level],
            quality,
            anchor,
            LEVEL_FALLBACKS[level],
        )
        if safe:
            d["scale"], d["crop_end"], d["headroom_ratio"] = safe
            d["zoom_level"] = d["reels_role"] = level
            d["reels_target_scale"] = d["state_cap"] = ZOOM_LEVELS[level]
            d["reels_scale_limited"] = (
                float(d["scale"]) + 0.005 < ZOOM_LEVELS[level]
            )


def _auto_slow_push(result: dict[str, Any]) -> int:
    """Use a slow push only for semantic builds (or explicit slow_push), never cadence/peaks."""
    changed = 0
    for d in result.get("decisions", []):
        if d.get("status") != "PLANNED" or bool(d.get("cadence_refresh")):
            continue
        if str(d.get("state", "CONTEXT")).upper() == "CONTEXT":
            continue
        if d.get("motion") == "hold":
            continue

        hint = str(d.get("motion_hint") or "auto").lower()
        direction = str(d.get("direction") or "").lower()
        level = str(d.get("zoom_level") or "")
        explicit = hint == "slow_push"
        automatic = hint in {"", "auto"} and direction == "build" and level in {"Z2", "Z3"}
        if not (explicit or automatic):
            continue

        if d.get("motion") != "slow_push":
            d["motion"] = "slow_push"
            changed += 1
        if automatic:
            d["auto_slow_push"] = True
            d["slow_push_reason"] = "semantic_build"
    return changed


def _slow_push_settle(result: dict[str, Any]) -> int:
    changed = 0
    for d in result.get("decisions", []):
        if d.get("status") != "PLANNED" or d.get("motion") != "slow_push":
            continue
        start, end = int(d.get("start_ms", 0)), int(d.get("end_ms", 0))
        max_transition = end - start - MIN_SETTLE_MS
        if max_transition < MIN_PUSH_MS:
            d["motion"], d["transition_end_ms"] = "step", start
            d["slow_push_fallback"] = "step_no_settle_room"
            changed += 1
            continue

        transition = min(SLOW_PUSH_TARGET_MS, max_transition)
        if transition < MIN_PUSH_MS:
            d["motion"], d["transition_end_ms"] = "step", start
            d["slow_push_fallback"] = "step_transition_too_short"
            changed += 1
            continue

        previous = max(0, int(d.get("transition_end_ms", start)) - start)
        d["transition_end_ms"] = start + transition
        d["slow_push_transition_ms"] = transition
        d["slow_push_settle_ms"] = end - d["transition_end_ms"]
        changed += int(previous != transition)
    return changed


def _hold(d: dict[str, Any], reason: str) -> None:
    d["motion"] = "hold"
    d["crop_end"] = list(d.get("crop_start") or d.get("crop_end") or [])
    d["transition_end_ms"] = int(d.get("start_ms", 0))
    d["auto_return"] = False
    d["continued_by_next"] = True
    d["continuation_reason"] = reason


def _same_block(
    result: dict[str, Any], events: list[dict[str, Any]], grace: int
) -> int:
    decisions = {
        str(d.get("event_id")): d
        for d in result.get("decisions", [])
        if d.get("status") == "PLANNED"
    }
    by_id = {str(e.get("id")): e for e in events}
    index = {str(e.get("id")): i for i, e in enumerate(events)}
    suppressed: set[str] = set()
    for ret in result.get("returns", []):
        pid = str(ret.get("parent_event_id") or "")
        parent, pi = by_id.get(pid), index.get(pid)
        if parent is None or pi is None or pi + 1 >= len(events):
            continue
        nxt = events[pi + 1]
        nd = decisions.get(str(nxt.get("id") or ""))
        pd = decisions.get(pid)
        if (
            pd is None
            or nd is None
            or str(nxt.get("direction") or "").lower() == "release"
        ):
            continue
        if str(parent.get("block_id") or "") != str(nxt.get("block_id") or ""):
            continue
        return_ms = int(ret.get("start_ms", 0))
        if int(nd.get("start_ms", nxt.get("t_ms", 0))) - return_ms > grace:
            continue
        suppressed.add(pid)
        pd["auto_return"], pd["continued_by_next"], pd["continuation_reason"] = (
            False,
            True,
            "same_block",
        )
        if pd.get("zoom_level") and pd.get("zoom_level") == nd.get("zoom_level"):
            nd["crop_end"] = list(pd.get("crop_end") or nd.get("crop_end") or [])
            nd["scale"] = pd.get("scale", nd.get("scale"))
            _hold(nd, "same_block_same_level_hold")
    if suppressed:
        result["returns"] = [
            r
            for r in result.get("returns", [])
            if str(r.get("parent_event_id") or "") not in suppressed
        ]
    return len(suppressed)


def _coalesce_fast(result: dict[str, Any]) -> int:
    visible = sorted(
        [
            d
            for d in result.get("decisions", [])
            if d.get("status") == "PLANNED"
            and d.get("motion") != "hold"
            and d.get("crop_start") != d.get("crop_end")
        ],
        key=lambda d: int(d.get("start_ms", 0)),
    )
    kept: list[dict[str, Any]] = []
    suppressed_ids: set[str] = set()
    count = 0
    for current in visible:
        drop_current = False
        while (
            kept
            and int(current.get("start_ms", 0))
            - int(kept[-1].get("start_ms", 0))
            < MIN_GAP_MS
        ):
            previous = kept[-1]
            if LEVEL_RANK.get(str(current.get("zoom_level")), 0) > LEVEL_RANK.get(
                str(previous.get("zoom_level")), 0
            ):
                _hold(previous, "rapid_change_stronger_next")
                suppressed_ids.add(str(previous.get("event_id") or ""))
                kept.pop()
                count += 1
            else:
                _hold(current, "rapid_change_coalesced")
                suppressed_ids.add(str(current.get("event_id") or ""))
                count += 1
                drop_current = True
                break
        if not drop_current:
            kept.append(current)
    if suppressed_ids:
        result["returns"] = [
            r
            for r in result.get("returns", [])
            if str(r.get("parent_event_id") or "") not in suppressed_ids
        ]
    return count


def _short_home(result: dict[str, Any]) -> int:
    visible = sorted(
        [
            d
            for d in result.get("decisions", [])
            if d.get("status") == "PLANNED"
            and d.get("motion") != "hold"
            and d.get("crop_start") != d.get("crop_end")
        ],
        key=lambda d: int(d.get("start_ms", 0)),
    )
    kept: list[dict[str, Any]] = []
    count = 0
    for ret in sorted(result.get("returns", []), key=lambda r: int(r.get("start_ms", 0))):
        t = int(ret.get("start_ms", 0))
        nxt = next((d for d in visible if int(d.get("start_ms", 0)) > t), None)
        if nxt is not None and int(nxt.get("start_ms", 0)) - t < MIN_GAP_MS:
            count += 1
            continue
        kept.append(ret)
    result["returns"] = kept
    return count


def _fixed_changes(
    duration: int,
    cuts: list[int],
    decisions: list[dict[str, Any]],
    returns: list[dict[str, Any]],
) -> list[int]:
    times = {0, duration, *[max(0, min(duration, int(t))) for t in cuts]}
    times.update(
        int(d.get("start_ms", 0))
        for d in decisions
        if d.get("status") == "PLANNED"
        and d.get("motion") != "hold"
        and d.get("crop_start") != d.get("crop_end")
    )
    times.update(
        int(r.get("start_ms", 0))
        for r in returns
        if r.get("crop_start") != r.get("crop_end")
    )
    return sorted(t for t in times if 0 <= t <= duration)


def _cadence_requests(
    duration: int,
    cuts: list[int],
    decisions: list[dict[str, Any]],
    returns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    known, requests = _fixed_changes(duration, cuts, decisions, returns), []
    for left, right in zip(known, known[1:]):
        cursor = left
        while right - cursor > MAX_GAP_MS:
            lo = cursor + MIN_GAP_MS
            hi = min(cursor + MAX_GAP_MS, right - MIN_GAP_MS)
            if hi < lo:
                break
            at = max(lo, min(cursor + PREFERRED_GAP_MS, hi))
            requests.append(
                {
                    "at_ms": at,
                    "window_start_ms": lo,
                    "window_end_ms": hi,
                    "semantic_trigger": False,
                }
            )
            cursor = at
    return requests


def _candidate_ok(row: dict[str, Any]) -> bool:
    if any(
        bool(row.get(k, False))
        for k in (
            "blink",
            "blur",
            "hard_block",
            "eyes_closed",
            "long_eye_closure",
            "pose_unsafe",
            "strong_head_turn",
        )
    ):
        return False
    if row.get("ear") is not None and float(row["ear"]) < 0.20:
        return False
    if row.get("mar") is not None and float(row["mar"]) > 0.45:
        return False
    if row.get("laplacian_var") is not None and float(row["laplacian_var"]) < 60:
        return False
    flow = row.get("flow_speed_px") or row.get("motion_speed_px")
    return not (flow is not None and float(flow) > 2.0)


def _materialize_cadence(
    result: dict[str, Any],
    prepared: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    w, h = int(result["source"]["width"]), int(result["source"]["height"])
    obs = sorted(
        list(prepared.get("observations") or []), key=lambda o: int(o["t_ms"])
    )
    if not obs:
        return [], requests
    window = int((result.get("config") or {}).get("window_ms", 1200))
    quality = float(prepared.get("source", {}).get("quality_cap", ABS_CAP))
    anchor = core._get_global_anchor(obs)
    fixed: list[tuple[int, list[int]]] = []
    for d in result.get("decisions", []):
        if d.get("status") == "PLANNED":
            fixed.append((int(d.get("start_ms", 0)), list(d.get("crop_end") or [])))
    for r in result.get("returns", []):
        fixed.append((int(r.get("start_ms", 0)), list(r.get("crop_end") or [])))
    fixed.sort()
    crop, fi, out, unresolved = [0, 0, w, h], 0, [], []
    for i, req in enumerate(sorted(requests, key=lambda x: int(x["at_ms"]))):
        desired = int(req["at_ms"])
        while fi < len(fixed) and fixed[fi][0] <= desired:
            if fixed[fi][1]:
                crop = list(fixed[fi][1])
            fi += 1
        current_scale = _scale(crop, w, h)
        if current_scale > ZOOM_LEVELS[CADENCE_MAX_LEVEL] + 0.01:
            unresolved.append({**req, "reason": "semantic_framing_has_priority"})
            continue
        candidates = [
            r
            for r in obs
            if int(req["window_start_ms"]) <= int(r["t_ms"]) <= int(req["window_end_ms"])
            and _candidate_ok(r)
        ]
        if not candidates:
            unresolved.append({**req, "reason": "no_safe_visual_boundary"})
            continue
        candidates.sort(
            key=lambda r: (
                0 if r.get("head_return") else 1,
                abs(int(r["t_ms"]) - desired),
            )
        )
        at = int(candidates[0]["t_ms"])
        level = (
            "Z1"
            if current_scale <= 1.005
            or current_scale > ZOOM_LEVELS["Z1"] + 0.01
            else "Z2"
        )
        safe = _safe_crop(
            obs,
            at,
            at + window,
            w,
            h,
            window,
            ZOOM_LEVELS[level],
            quality,
            anchor,
            LEVEL_FALLBACKS[level],
        )
        if not safe:
            unresolved.append({**req, "reason": "no_safe_low_level_crop"})
            continue
        scale, target, headroom = safe
        out.append(
            {
                "event_id": f"cadence_{level.lower()}_{i:03d}",
                "event_ms": desired,
                "start_ms": at,
                "end_ms": at,
                "transition_end_ms": at,
                "status": "PLANNED",
                "state": "SOFT",
                "base_desired_state": "SOFT",
                "desired_state": "SOFT",
                "direction": "cadence_refresh",
                "motion": "step",
                "motion_hint": "step",
                "crop_start": list(crop),
                "crop_end": list(target),
                "scale": scale,
                "state_cap": ZOOM_LEVELS[level],
                "why": "cadence_low_level_refresh",
                "semantic_trigger": False,
                "cadence_refresh": True,
                "zoom_level": level,
                "reels_role": f"CADENCE_{level}",
                "headroom_ratio": headroom,
            }
        )
        crop = list(target)
    return out, unresolved


def _normalize(result: dict[str, Any]) -> None:
    w, h = int(result["source"]["width"]), int(result["source"]["height"])
    crop, items = [0, 0, w, h], []
    items.extend(
        (int(d.get("start_ms", 0)), 1, d)
        for d in result.get("decisions", [])
        if d.get("status") == "PLANNED"
    )
    items.extend(
        (int(r.get("start_ms", 0)), 0, r) for r in result.get("returns", [])
    )
    for _, _, item in sorted(items, key=lambda x: (x[0], x[1])):
        item["crop_start"] = list(crop)
        if item.get("motion") == "hold":
            item["crop_end"] = list(crop)
        crop = list(item.get("crop_end") or crop)


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    duration = int(result.get("source", {}).get("duration_ms") or 0)
    changes = [
        (int(d.get("start_ms", 0)), d)
        for d in result.get("decisions", [])
        if d.get("status") == "PLANNED"
        and d.get("motion") != "hold"
        and d.get("crop_start") != d.get("crop_end")
    ]
    times = sorted(
        [t for t, _ in changes]
        + [
            int(r.get("start_ms", 0))
            for r in result.get("returns", [])
            if r.get("crop_start") != r.get("crop_end")
        ]
    )
    gaps = [b - a for a, b in zip(times, times[1:])]
    counts = {k: 0 for k in ZOOM_LEVELS}
    for _, d in changes:
        if d.get("zoom_level") in counts:
            counts[d["zoom_level"]] += 1
    return {
        "visible_framing_change_count": len(times),
        "semantic_change_count": sum(
            not bool(d.get("cadence_refresh")) for _, d in changes
        ),
        "cadence_low_level_change_count": sum(
            bool(d.get("cadence_refresh")) for _, d in changes
        ),
        "zoom_level_counts": counts,
        "framing_changes_per_min": (
            round((len(times) * 60000 / duration), 2) if duration else 0.0
        ),
        "median_gap_between_framing_changes_ms": int(median(gaps)) if gaps else None,
        "minimum_gap_between_framing_changes_ms": min(gaps) if gaps else None,
        "cadence_min_gap_ms": MIN_GAP_MS,
        "cadence_preferred_gap_ms": PREFERRED_GAP_MS,
        "cadence_max_gap_ms": MAX_GAP_MS,
    }


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    prepared, events = _prepare(payload)
    old_duration = core._zoom_duration
    core._zoom_duration = _duration
    try:
        result = core.plan(prepared)
    finally:
        core._zoom_duration = old_duration

    _retarget(result, prepared)
    auto_push = _auto_slow_push(result)
    slow = _slow_push_settle(result)
    grace = max(
        0,
        int(
            (payload.get("config") or {}).get(
                "same_block_continuation_ms", SAME_BLOCK_MS
            )
        ),
    )
    same = _same_block(result, events, grace)
    rapid = _coalesce_fast(result)
    short_home = _short_home(result)
    duration = int(result.get("source", {}).get("duration_ms") or 0)
    cuts = [int(x) for x in prepared.get("content_cuts_ms", [])]
    requests = _cadence_requests(
        duration,
        cuts,
        list(result.get("decisions") or []),
        list(result.get("returns") or []),
    )
    cadence, unresolved = _materialize_cadence(result, prepared, requests)
    result.setdefault("decisions", []).extend(cadence)
    _normalize(result)

    result["version"] = VERSION
    result["cadence_requests"] = unresolved
    result["cadence_low_level_changes"] = len(cadence)
    result["same_block_returns_suppressed"] = same
    result["rapid_semantic_changes_coalesced"] = rapid
    result["short_home_flashes_suppressed"] = short_home
    result["auto_slow_pushes"] = auto_push
    result["slow_push_adjusted"] = slow
    result.setdefault("config", {}).update(
        {
            "same_block_continuation_ms": grace,
            "reels_cadence": {
                "min_change_gap_ms": MIN_GAP_MS,
                "preferred_change_gap_ms": PREFERRED_GAP_MS,
                "max_change_gap_ms": MAX_GAP_MS,
            },
            "reels_scales": {"HOME": HOME, **ZOOM_LEVELS},
            "semantic_importance_thresholds": {
                "Z2_effective": Z2_IMPORTANCE,
                "Z3_effective": Z3_IMPORTANCE,
                "Z4_raw_semantic": Z4_RAW_IMPORTANCE,
            },
            "cadence_max_level": CADENCE_MAX_LEVEL,
            "absolute_zoom_cap": ABS_CAP,
            "state_caps": {
                "CONTEXT": HOME,
                "SOFT": 1.06,
                "ARGUMENT": 1.09,
                "EMPHASIS": 1.13,
            },
            "min_visible_framing_ms": MIN_GAP_MS,
            "slow_push_target_ms": SLOW_PUSH_TARGET_MS,
            "min_slow_push_ms": MIN_PUSH_MS,
            "min_slow_push_settle_ms": MIN_SETTLE_MS,
        }
    )
    result["rhythm_summary"] = _summary(result)
    visual = {0, duration, *cuts}
    visual.update(
        int(d.get("start_ms", 0))
        for d in result.get("decisions", [])
        if d.get("status") == "PLANNED"
        and d.get("motion") != "hold"
        and d.get("crop_start") != d.get("crop_end")
    )
    visual.update(
        int(r.get("start_ms", 0))
        for r in result.get("returns", [])
        if r.get("crop_start") != r.get("crop_end")
    )
    result["visual_change_times_ms"] = sorted(
        t for t in visual if 0 <= t <= duration
    )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Plan v1.7.6 calmer Reels four-level semantic + cadence framing"
    )
    p.add_argument("input_json")
    p.add_argument("output_json")
    args = p.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    Path(args.output_json).write_text(
        json.dumps(plan(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
