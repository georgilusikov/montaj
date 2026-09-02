#!/usr/bin/env python3
"""Research-aligned editorial-energy director for v1.7.6 A/B testing.

This branch deliberately changes only directing policy. Geometry, boundary safety,
headroom, renderer and QC remain inherited from the stable v1.7.6 core.

Key policy:
- semantics choose target framing;
- editorial-energy slope chooses HOW to move there;
- cadence only emits refresh requests, never synthetic zoom events;
- opening motion is semantic/optional, never mandatory;
- 3 s is no longer a hard anti-chatter floor; hard floor is ~1.2 s;
- slow pushes prefer ~0.9 s of stable settle when there is enough room.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any, Callable

import zoom_planner_v176 as core

VERSION = "1.7.6-research-aligned"
HOME = 1.00
ZOOM_LEVELS = {"Z1": 1.03, "Z2": 1.05, "Z3": 1.08, "Z4": 1.13}
LEVEL_FALLBACKS = {
    "Z1": (1.03, 1.02),
    "Z2": (1.05, 1.04, 1.03),
    "Z3": (1.08, 1.07, 1.06),
    "Z4": (1.13, 1.12, 1.11, 1.10),
}
ARTISTIC_CAP = 1.13

# Timing is a guard rail, not a semantic generator.
HARD_CHANGE_FLOOR_MS = 1200
PREFERRED_SEMANTIC_DWELL_MS = 2400
PREFERRED_GAP_MS = 4500
MAX_STATIC_GAP_MS = 6000

# Slow push: retain the old hard safety minimum, but prefer a longer readable settle.
SLOW_PUSH_TARGET_MS = 2000
MIN_PUSH_MS = 1200
HARD_MIN_SETTLE_MS = 500
PREFERRED_SETTLE_MS = 900

ENERGY_RISE_SLOW = 0.08
ENERGY_RISE_PUNCH = 0.20


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _event_energy(event: dict[str, Any]) -> float:
    """Editorial energy is an internal directing signal, not measured viewer attention."""
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


def _trend(delta: float | None) -> str:
    if delta is None:
        return "hold"
    if delta >= ENERGY_RISE_PUNCH:
        return "rise_fast"
    if delta >= ENERGY_RISE_SLOW:
        return "rise"
    if delta <= -0.18:
        return "fall_fast"
    if delta <= -0.07:
        return "fall"
    return "hold"


def _annotate_real_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate real semantics without letting energy manufacture target scale."""
    annotated: list[dict[str, Any]] = []
    previous_energy: float | None = None

    for raw in sorted(events, key=lambda e: (int(e.get("t_ms", 0)), str(e.get("id", "")))):
        event = copy.deepcopy(raw)
        energy = _event_energy(event)
        delta = None if previous_energy is None else energy - previous_energy
        trend = _trend(delta)
        direction = str(event.get("direction") or "").lower()

        event["editorial_energy"] = round(energy, 4)
        event["energy_trend"] = trend
        event["energy_generated"] = False
        event["semantic_trigger"] = True
        event.setdefault("semantic_importance", float(raw.get("importance", energy) or energy))

        # Preserve semantic importance exactly. The semantic core still chooses Z1-Z4.
        # Energy only selects motion when the agent did not explicitly choose one.
        hint = str(event.get("motion_hint") or "auto").lower()
        if hint in {"", "auto"}:
            if direction in {"peak", "ratchet_1", "ratchet_2", "ratchet_3", "release"}:
                event["motion_hint"] = "step"
            elif trend == "rise":
                event["motion_hint"] = "slow_push"
            elif previous_energy is None and direction == "build":
                event["motion_hint"] = "slow_push"
            else:
                # Includes sharp rise, flat energy and falls: use a discrete reframe.
                event["motion_hint"] = "step"

        annotated.append(event)
        previous_energy = energy

    return annotated


def _energy_points(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "t_ms": int(e.get("t_ms", 0)),
            "energy": float(e.get("editorial_energy", _event_energy(e))),
            "block_id": str(e.get("block_id") or ""),
            "source": "semantic",
            "event_id": str(e.get("id") or ""),
        }
        for e in sorted(events, key=lambda x: int(x.get("t_ms", 0)))
    ]


def _prepare_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    prepared = copy.deepcopy(payload)
    events = _annotate_real_events(list(prepared.get("semantic_events") or []))
    prepared["semantic_events"] = events
    prepared.setdefault("config", {}).setdefault("same_block_continuation_ms", 2000)
    return prepared, events


def _research_duration(event: dict[str, Any], start_ms: int) -> tuple[str, int]:
    """Use semantic episode duration with a ~1.2 s hard floor, not a 3 s hard floor."""
    explicit = str(event.get("zoom_duration_type") or "").lower()
    raw = int(event.get("semantic_duration_ms") or 0)
    if raw <= 0:
        semantic_start = int(event.get("semantic_start_ms", event.get("t_ms", start_ms)))
        raw = max(0, int(event.get("end_ms", semantic_start)) - semantic_start)

    bands = core.core.ZOOM_DURATION_BANDS_MS
    if explicit in bands:
        kind = explicit
    elif raw and raw < 1500:
        kind = "micro_punch"
    elif raw and raw < 2500:
        kind = "beat"
    elif raw:
        kind = "argument_hold"
    else:
        kind = "beat"

    lo, hi, default = bands[kind]
    semantic_visual = default if raw <= 0 else int(core.core._clamp(raw, lo, hi))
    return kind, max(HARD_CHANGE_FLOOR_MS, semantic_visual)


def _requests_only(
    result: dict[str, Any],
    prepared: dict[str, Any],
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cadence may ask for a refresh, but may not invent a camera move in this variant."""
    unresolved = []
    for req in requests:
        unresolved.append(
            {
                **req,
                "why": "static_visual_gap_refresh_request",
                "preferred_action": "content_cut_or_caption_then_optional_z1",
                "fallback_action": "hold",
                "semantic_trigger": False,
                "research_aligned": True,
            }
        )
    return [], unresolved


def _patch_core() -> dict[str, Any]:
    old = {
        "ZOOM_LEVELS": core.ZOOM_LEVELS,
        "LEVEL_FALLBACKS": core.LEVEL_FALLBACKS,
        "ABS_CAP": core.ABS_CAP,
        "MIN_GAP_MS": core.MIN_GAP_MS,
        "PREFERRED_GAP_MS": core.PREFERRED_GAP_MS,
        "MAX_GAP_MS": core.MAX_GAP_MS,
        "_duration": core._duration,
        "_materialize_cadence": core._materialize_cadence,
    }
    core.ZOOM_LEVELS = dict(ZOOM_LEVELS)
    core.LEVEL_FALLBACKS = dict(LEVEL_FALLBACKS)
    core.ABS_CAP = ARTISTIC_CAP
    core.MIN_GAP_MS = HARD_CHANGE_FLOOR_MS
    core.PREFERRED_GAP_MS = PREFERRED_GAP_MS
    core.MAX_GAP_MS = MAX_STATIC_GAP_MS
    core._duration = _research_duration
    core._materialize_cadence = _requests_only
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
        for key in ("editorial_energy", "energy_trend", "energy_generated", "semantic_trigger"):
            if key in event:
                decision[key] = event[key]
        decision["energy_role"] = "motion_only"


def _prefer_readable_settle(result: dict[str, Any]) -> int:
    """Prefer ~0.9 s stable framing after a slow push when the episode has room."""
    changed = 0
    for decision in result.get("decisions", []):
        if decision.get("status") != "PLANNED" or decision.get("motion") != "slow_push":
            continue
        start = int(decision.get("start_ms", 0))
        end = int(decision.get("end_ms", start))
        total = max(0, end - start)
        if total < MIN_PUSH_MS + HARD_MIN_SETTLE_MS:
            continue

        preferred_room = total >= MIN_PUSH_MS + PREFERRED_SETTLE_MS
        settle_target = PREFERRED_SETTLE_MS if preferred_room else HARD_MIN_SETTLE_MS
        transition = min(SLOW_PUSH_TARGET_MS, total - settle_target)
        if transition < MIN_PUSH_MS:
            continue

        previous = int(decision.get("transition_end_ms", start))
        decision["transition_end_ms"] = start + transition
        decision["slow_push_transition_ms"] = transition
        decision["slow_push_settle_ms"] = end - decision["transition_end_ms"]
        decision["slow_push_preferred_settle_met"] = decision["slow_push_settle_ms"] >= PREFERRED_SETTLE_MS
        changed += int(previous != decision["transition_end_ms"])
    return changed


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    prepared, events = _prepare_payload(payload)
    old = _patch_core()
    try:
        result = core.plan(prepared)
    finally:
        _restore_core(old)

    _annotate_result(result, events)
    settle_adjusted = _prefer_readable_settle(result)

    result["version"] = VERSION
    result["editorial_energy_curve"] = _energy_points(events)
    result["generated_energy_events"] = 0
    result["intro_energy_events_added"] = 0
    result["energy_checkpoints_added"] = 0
    result["intro_energy_movement"] = "SEMANTIC_ONLY"
    result["cadence_low_level_changes"] = 0
    result["research_settle_adjusted"] = settle_adjusted

    # Core generated the long-gap requests, but _requests_only prevented synthetic zooms.
    result["refresh_requests"] = list(result.get("cadence_requests") or [])

    cfg = result.setdefault("config", {})
    cfg.update(
        {
            "editorial_energy_enabled": True,
            "editorial_energy_role": "motion_only",
            "semantic_role": "target_framing",
            "synthetic_energy_events_enabled": False,
            "mandatory_opening_motion": False,
            "cadence_materializes_zoom": False,
            "energy_zoom_levels": {"HOME": HOME, **ZOOM_LEVELS},
            "absolute_zoom_cap": ARTISTIC_CAP,
            "state_caps": {"CONTEXT": HOME, "SOFT": 1.05, "ARGUMENT": 1.08, "EMPHASIS": 1.13},
            "hard_change_floor_ms": HARD_CHANGE_FLOOR_MS,
            "preferred_semantic_dwell_ms": PREFERRED_SEMANTIC_DWELL_MS,
            "preferred_static_gap_ms": PREFERRED_GAP_MS,
            "max_static_gap_ms": MAX_STATIC_GAP_MS,
            "slow_push_target_ms": SLOW_PUSH_TARGET_MS,
            "slow_push_hard_min_settle_ms": HARD_MIN_SETTLE_MS,
            "slow_push_preferred_settle_ms": PREFERRED_SETTLE_MS,
            "energy_cadence_role": "diagnostic_refresh_request_only",
        }
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan v1.7.6 research-aligned semantic-energy framing")
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
