#!/usr/bin/env python3
"""Editorial-energy director over the stable v1.7.6 Reels zoom adapter.

This layer does not replace geometry, boundary selection, safety, cadence or rendering.
It derives a lightweight editorial-energy curve from existing semantic events, adds a
short intro ramp, and inserts sparse energy checkpoints so camera framing can rise,
hold, ease back or release instead of being driven mainly by a timer.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import zoom_planner_v176 as core

VERSION = "1.7.6-energy"
HOME = 1.00
ZOOM_LEVELS = {"Z1": 1.03, "Z2": 1.05, "Z3": 1.08, "Z4": 1.12}
LEVEL_FALLBACKS = {
    "Z1": (1.03, 1.02),
    "Z2": (1.05, 1.04, 1.03),
    "Z3": (1.08, 1.07, 1.06),
    "Z4": (1.12, 1.11, 1.10, 1.09),
}
ARTISTIC_CAP = 1.12

# Cadence remains a guard rail, not the director. Semantic/energy events may happen
# inside this window when meaning justifies them; timer-only refresh waits longer.
MIN_GAP_MS = 3000
PREFERRED_GAP_MS = 4500
MAX_GAP_MS = 6000
ENERGY_CHECKPOINT_MS = 4500
ENERGY_CLEARANCE_MS = 1600
ENERGY_RELEASE = 0.36
ENERGY_RISE_SLOW = 0.08
ENERGY_RISE_PUNCH = 0.20
ENERGY_DECAY_PER_SEC = 0.035

# The first five seconds must not begin visually dead. We aim for a two-step low-level
# ramp; real semantic events may replace either synthetic step when they are nearby.
INTRO_END_MS = 5000
INTRO_POINTS = ((800, 0.48, "Z1"), (3900, 0.62, "Z2"))
INTRO_CLEARANCE_MS = 1400


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _event_energy(event: dict[str, Any]) -> float:
    """Convert existing semantic/performance salience into editorial energy 0..1."""
    effective = float(event.get("importance", event.get("semantic_importance", 0.0)) or 0.0)
    direction = str(event.get("direction") or "").lower()
    if direction == "release":
        return 0.24
    energy = effective
    if direction in {"peak", "ratchet_3"}:
        energy = max(energy, 0.94)
    elif direction == "ratchet_2":
        energy = max(energy, 0.80)
    elif direction in {"build", "ratchet_1"}:
        energy = max(energy, 0.60)
    return _clamp(energy)


def _trend(delta: float) -> str:
    if delta >= ENERGY_RISE_PUNCH:
        return "rise_fast"
    if delta >= ENERGY_RISE_SLOW:
        return "rise"
    if delta <= -0.18:
        return "fall_fast"
    if delta <= -0.07:
        return "fall"
    return "hold"


def _safe_observation(observations: list[dict[str, Any]], target_ms: int) -> dict[str, Any] | None:
    if not observations:
        return None
    ranked = sorted(
        observations,
        key=lambda row: (
            0 if core._candidate_ok(row) else 1,
            0 if row.get("head_return") else 1,
            abs(int(row.get("t_ms", 0)) - target_ms),
        ),
    )
    return ranked[0] if ranked and core._candidate_ok(ranked[0]) else None


def _boundary_candidate(observations: list[dict[str, Any]], target_ms: int, event_id: str) -> tuple[int, dict[str, Any]] | None:
    row = _safe_observation(observations, target_ms)
    if row is None:
        return None
    ms = int(row.get("t_ms", target_ms))
    candidate = {
        "id": f"{event_id}_boundary",
        "ms": ms,
        "word_boundary": False,
        "pause": False,
        "head_return": bool(row.get("head_return", False)),
    }
    for key in ("ear", "mar", "laplacian_var", "flow_speed_px", "motion_speed_px"):
        if row.get(key) is not None:
            candidate[key] = row[key]
    return ms, candidate


def _synthetic_event(
    *,
    observations: list[dict[str, Any]],
    event_id: str,
    target_ms: int,
    energy: float,
    block_id: str,
    reason: str,
    previous_energy: float,
    intro: bool = False,
) -> dict[str, Any] | None:
    chosen = _boundary_candidate(observations, target_ms, event_id)
    if chosen is None:
        return None
    ms, candidate = chosen
    energy = _clamp(energy)
    delta = energy - previous_energy
    trend = _trend(delta)
    direction = "release" if energy < ENERGY_RELEASE else None
    motion_hint = "step"
    if direction != "release" and ENERGY_RISE_SLOW <= delta < ENERGY_RISE_PUNCH:
        motion_hint = "slow_push"
    elif intro and direction != "release":
        motion_hint = "slow_push"

    event = {
        "id": event_id,
        "t_ms": ms,
        "accent_ms": ms,
        "end_ms": ms + 900,
        "semantic_start_ms": ms,
        "semantic_duration_ms": 900,
        "importance": energy,
        # Generated energy points may shape Z1-Z3, but never manufacture Z4.
        "semantic_importance": min(energy, 0.84),
        "block_id": block_id,
        "boundary_candidates": [candidate],
        "motion_hint": motion_hint,
        "why": reason,
        "editorial_energy": round(energy, 4),
        "energy_trend": trend,
        "energy_generated": True,
        "semantic_trigger": False,
        "intro_energy": bool(intro),
    }
    if direction:
        event["direction"] = direction
    return event


def _annotate_real_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    previous_energy = 0.36
    previous_t = 0
    for raw in sorted(events, key=lambda e: (int(e.get("t_ms", 0)), str(e.get("id", "")))):
        event = copy.deepcopy(raw)
        t_ms = int(event.get("t_ms", 0))
        energy = _event_energy(event)

        # During the first five seconds, do not let the editorial curve drift downward.
        # Explicit peaks/releases remain explicit; ordinary hook/setup material gets a
        # mild rising floor so the opening feels progressively more alive.
        direction = str(event.get("direction") or "").lower()
        if t_ms <= INTRO_END_MS and direction not in {"release", "peak", "ratchet_3"}:
            progress = _clamp(t_ms / max(INTRO_END_MS, 1))
            intro_floor = 0.44 + 0.18 * progress
            energy = max(energy, intro_floor, previous_energy)

        delta = energy - previous_energy
        trend = _trend(delta)
        event["editorial_energy"] = round(energy, 4)
        event["energy_trend"] = trend
        event["energy_generated"] = False
        event["semantic_trigger"] = True

        # Let energy choose the working zoom level while preserving raw semantic
        # importance separately for the strict Z4 gate.
        event["importance"] = energy
        event.setdefault("semantic_importance", float(raw.get("importance", energy) or energy))

        hint = str(event.get("motion_hint") or "auto").lower()
        if hint in {"", "auto"} and direction not in {"peak", "ratchet_2", "ratchet_3", "release"}:
            if ENERGY_RISE_SLOW <= delta < ENERGY_RISE_PUNCH:
                event["motion_hint"] = "slow_push"
            elif delta >= ENERGY_RISE_PUNCH:
                event["motion_hint"] = "step"

        # A large fall to genuinely low energy is a camera release. Smaller falls map
        # naturally to a lower Z-level rather than forcing HOME every time.
        if not direction and delta <= -0.22 and energy < 0.40:
            event["direction"] = "release"

        annotated.append(event)
        previous_energy = energy
        previous_t = t_ms
    return annotated


def _nearest_real_block(real_events: list[dict[str, Any]], t_ms: int) -> str:
    previous = [e for e in real_events if int(e.get("t_ms", 0)) <= t_ms]
    if previous:
        return str(previous[-1].get("block_id") or "__energy_curve__")
    following = [e for e in real_events if int(e.get("t_ms", 0)) > t_ms]
    if following:
        return str(following[0].get("block_id") or "__energy_curve__")
    return "__energy_curve__"


def _energy_points(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "t_ms": int(e.get("t_ms", 0)),
            "energy": float(e.get("editorial_energy", _event_energy(e))),
            "block_id": str(e.get("block_id") or "__energy_curve__"),
            "source": "generated" if e.get("energy_generated") else "semantic",
            "event_id": str(e.get("id") or ""),
        }
        for e in sorted(events, key=lambda x: int(x.get("t_ms", 0)))
    ]


def _energy_at(points: list[dict[str, Any]], t_ms: int) -> float:
    if not points:
        return 0.42
    prev = None
    nxt = None
    for point in points:
        if int(point["t_ms"]) <= t_ms:
            prev = point
        elif nxt is None:
            nxt = point
            break
    if prev and nxt:
        left, right = int(prev["t_ms"]), int(nxt["t_ms"])
        if right <= left:
            return _clamp(float(prev["energy"]))
        alpha = (t_ms - left) / (right - left)
        return _clamp(float(prev["energy"]) + (float(nxt["energy"]) - float(prev["energy"])) * alpha)
    if prev:
        elapsed_s = max(0.0, (t_ms - int(prev["t_ms"])) / 1000.0)
        return max(0.32, float(prev["energy"]) - ENERGY_DECAY_PER_SEC * elapsed_s)
    if nxt:
        lead_s = max(0.0, (int(nxt["t_ms"]) - t_ms) / 1000.0)
        return max(0.36, float(nxt["energy"]) - 0.025 * lead_s)
    return 0.42


def _inject_intro(
    events: list[dict[str, Any]], observations: list[dict[str, Any]], duration_ms: int
) -> tuple[list[dict[str, Any]], int]:
    out = list(events)
    added = 0
    previous_energy = 0.36
    for index, (target, energy, _) in enumerate(INTRO_POINTS, 1):
        if target >= duration_ms:
            continue
        nearby = [
            e for e in events
            if abs(int(e.get("t_ms", 0)) - target) <= INTRO_CLEARANCE_MS
            and str(e.get("direction") or "").lower() != "release"
            and float(e.get("importance", 0.0) or 0.0) >= 0.40
        ]
        if nearby:
            previous_energy = max(previous_energy, max(float(e.get("editorial_energy", 0.0) or 0.0) for e in nearby))
            continue
        block = _nearest_real_block(events, target) if events else "__intro_energy__"
        event = _synthetic_event(
            observations=observations,
            event_id=f"energy_intro_{index}",
            target_ms=target,
            energy=max(energy, previous_energy + 0.06),
            block_id=block,
            reason="intro_energy_ramp",
            previous_energy=previous_energy,
            intro=True,
        )
        if event:
            out.append(event)
            previous_energy = float(event["editorial_energy"])
            added += 1
    return sorted(out, key=lambda e: (int(e.get("t_ms", 0)), str(e.get("id", "")))), added


def _inject_checkpoints(
    events: list[dict[str, Any]],
    real_events: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    duration_ms: int,
) -> tuple[list[dict[str, Any]], int]:
    out = list(events)
    points = _energy_points(events)
    previous_energy = _energy_at(points, INTRO_END_MS)
    added = 0
    t_ms = INTRO_END_MS + ENERGY_CHECKPOINT_MS
    while t_ms < duration_ms:
        nearby = [e for e in events if abs(int(e.get("t_ms", 0)) - t_ms) <= ENERGY_CLEARANCE_MS]
        if nearby:
            previous_energy = _energy_at(points, t_ms)
            t_ms += ENERGY_CHECKPOINT_MS
            continue
        energy = _energy_at(points, t_ms)
        block = _nearest_real_block(real_events, t_ms)
        event = _synthetic_event(
            observations=observations,
            event_id=f"energy_checkpoint_{added:03d}",
            target_ms=t_ms,
            energy=energy,
            block_id=block,
            reason="editorial_energy_checkpoint",
            previous_energy=previous_energy,
            intro=False,
        )
        if event:
            out.append(event)
            points.append({
                "t_ms": int(event["t_ms"]),
                "energy": float(event["editorial_energy"]),
                "block_id": block,
                "source": "generated",
                "event_id": str(event["id"]),
            })
            points.sort(key=lambda p: int(p["t_ms"]))
            previous_energy = float(event["editorial_energy"])
            added += 1
        t_ms += ENERGY_CHECKPOINT_MS
    return sorted(out, key=lambda e: (int(e.get("t_ms", 0)), str(e.get("id", "")))), added


def _prepare_energy_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], int, int]:
    prepared = copy.deepcopy(payload)
    duration = int((prepared.get("source") or {}).get("duration_ms") or 0)
    observations = sorted(list(prepared.get("observations") or []), key=lambda o: int(o.get("t_ms", 0)))
    real_events = _annotate_real_events(list(prepared.get("semantic_events") or []))
    with_intro, intro_added = _inject_intro(real_events, observations, duration)
    directed, checkpoints_added = _inject_checkpoints(with_intro, real_events, observations, duration)
    prepared["semantic_events"] = directed
    prepared.setdefault("config", {}).setdefault("same_block_continuation_ms", 2000)
    return prepared, directed, intro_added, checkpoints_added


def _patch_core() -> dict[str, Any]:
    old = {
        "ZOOM_LEVELS": core.ZOOM_LEVELS,
        "LEVEL_FALLBACKS": core.LEVEL_FALLBACKS,
        "ABS_CAP": core.ABS_CAP,
        "MIN_GAP_MS": core.MIN_GAP_MS,
        "PREFERRED_GAP_MS": core.PREFERRED_GAP_MS,
        "MAX_GAP_MS": core.MAX_GAP_MS,
    }
    core.ZOOM_LEVELS = dict(ZOOM_LEVELS)
    core.LEVEL_FALLBACKS = dict(LEVEL_FALLBACKS)
    core.ABS_CAP = ARTISTIC_CAP
    core.MIN_GAP_MS = MIN_GAP_MS
    core.PREFERRED_GAP_MS = PREFERRED_GAP_MS
    core.MAX_GAP_MS = MAX_GAP_MS
    return old


def _restore_core(old: dict[str, Any]) -> None:
    for key, value in old.items():
        setattr(core, key, value)


def _annotate_result(result: dict[str, Any], events: list[dict[str, Any]]) -> None:
    by_id = {str(e.get("id")): e for e in events}
    for decision in result.get("decisions", []):
        event = by_id.get(str(decision.get("event_id") or ""))
        if not event:
            continue
        for key in ("editorial_energy", "energy_trend", "energy_generated", "semantic_trigger", "intro_energy"):
            if key in event:
                decision[key] = event[key]
        if event.get("energy_generated"):
            decision["why"] = event.get("why", decision.get("why"))


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    prepared, events, intro_added, checkpoints_added = _prepare_energy_payload(payload)
    old = _patch_core()
    try:
        result = core.plan(prepared)
    finally:
        _restore_core(old)

    _annotate_result(result, events)
    result["version"] = VERSION
    result["editorial_energy_curve"] = _energy_points(events)
    result["intro_energy_events_added"] = intro_added
    result["energy_checkpoints_added"] = checkpoints_added

    intro_visible = [
        d for d in result.get("decisions", [])
        if d.get("status") == "PLANNED"
        and int(d.get("start_ms", 0)) < INTRO_END_MS
        and d.get("motion") != "hold"
        and d.get("crop_start") != d.get("crop_end")
    ]
    result["intro_energy_movement"] = "PASS" if intro_visible else "VETOED_OR_MISSING"

    cfg = result.setdefault("config", {})
    cfg.update({
        "editorial_energy_enabled": True,
        "energy_zoom_levels": {"HOME": HOME, **ZOOM_LEVELS},
        "absolute_zoom_cap": ARTISTIC_CAP,
        "state_caps": {"CONTEXT": HOME, "SOFT": 1.05, "ARGUMENT": 1.08, "EMPHASIS": 1.12},
        "intro_energy_window_ms": INTRO_END_MS,
        "energy_checkpoint_ms": ENERGY_CHECKPOINT_MS,
        "energy_release_threshold": ENERGY_RELEASE,
        "energy_cadence_role": "guard_rail_only",
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan v1.7.6 editorial-energy Reels framing")
    parser.add_argument("input_json")
    parser.add_argument("output_json")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    Path(args.output_json).write_text(
        json.dumps(plan(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
