from __future__ import annotations

from typing import Any

from .assembler import materialize_framing_decision
from .coverage import synthesize_source_base_coverage
from .planner import plan_geometry_core
from .schema import FrameObservation, QualityMetrics, ShotState, sha256_canonical
from .semantic_bridge import plan_transition_from_semantic_context
from .timeline import ContentEdit, build_timeline_manifest
from .validator import validate_manifest_pre_render
from .when_solver import BoundaryCandidate

HOOK_SCALE_CAP = 1.16


def _quality(payload: dict[str, Any]) -> QualityMetrics:
    return QualityMetrics(
        width=int(payload["width"]),
        height=int(payload["height"]),
        sharpness=float(payload.get("sharpness", 1.0)),
        noise=float(payload.get("noise", 0.0)),
        compression=float(payload.get("compression", 0.0)),
    )


def _observations(items: list[dict[str, Any]]) -> list[FrameObservation]:
    return [FrameObservation(**item) for item in items]


def _content_edits(items: list[dict[str, Any]]) -> list[ContentEdit]:
    return [ContentEdit(**item) for item in items]


def _boundary_candidates(items: list[dict[str, Any]]) -> list[BoundaryCandidate]:
    return [BoundaryCandidate(**item) for item in items]


def plan_project(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute deterministic v1.7.1 planning from a frozen JSON-compatible payload."""
    analysis = dict(payload.get("analysis") or {})
    config = dict(payload.get("config") or {})
    if "quality" not in analysis or "observations" not in analysis:
        raise ValueError("analysis.quality and analysis.observations are required")

    quality = _quality(dict(analysis["quality"]))
    observations = _observations(list(analysis["observations"]))
    source_type = str(config.get("source_type", "live"))
    pace = str(config.get("pace", "neutral"))
    intensity = str(config.get("intensity", "moderate"))
    events = sorted(
        list(payload.get("semantic_events") or []),
        key=lambda item: (int(item["t_ms"]), str(item.get("event_id", ""))),
    )

    geometry = plan_geometry_core(
        observations=observations,
        quality=quality,
        intensity=intensity,
        pace=pace,
        wide_boost=bool(config.get("wide_boost", False)),
        wide_boost_cap=(
            float(config["wide_boost_cap"])
            if config.get("wide_boost_cap") is not None
            else None
        ),
        window_ms=int(config.get("window_ms", 500)),
        config_payload=config,
    )

    has_hook = any(bool(dict(event.get("context") or {}).get("is_hook", False)) for event in events)
    hook_geometry = None
    if has_hook:
        hook_geometry = plan_geometry_core(
            observations=observations,
            quality=quality,
            intensity=intensity,
            pace=pace,
            wide_boost=False,
            wide_boost_cap=None,
            style_cap_max=HOOK_SCALE_CAP,
            window_ms=int(config.get("window_ms", 500)),
            config_payload={
                "base_config": config,
                "geometry_mode": "hook",
                "wide_boost": False,
                "style_cap_max": HOOK_SCALE_CAP,
            },
        )

    current_state = ShotState(str(payload.get("initial_state", ShotState.CONTEXT.value)))
    current_scale = float(payload.get("initial_scale", 1.0))
    if current_scale < 1.0:
        raise ValueError("initial_scale <1.00 is forbidden")

    framing = []
    decisions: list[dict[str, object]] = []
    for index, event in enumerate(events):
        context = dict(event.get("context") or {})
        is_hook = bool(context.get("is_hook", False))
        event_geometry = hook_geometry if is_hook else geometry
        if event_geometry is None:
            raise AssertionError("hook geometry missing")

        transition = plan_transition_from_semantic_context(
            context,
            geometry_result=event_geometry,
            semantic_at_ms=int(event["t_ms"]),
            current_state=current_state,
            current_scale=current_scale,
            boundary_candidates=_boundary_candidates(list(event.get("boundary_candidates") or [])),
            profile=source_type,
            segment_start_ms=int(event.get("segment_start_ms", 0)),
            history_penalty=dict(event.get("history_penalty") or {}),
            pace=pace,
        )
        decisions.append({
            "event_id": str(event.get("event_id", f"event_{index:04d}")),
            "status": transition.get("status"),
            "desired_state": transition.get("desired_state"),
            "degraded": transition.get("degraded"),
            "is_hook": is_hook,
        })
        if transition.get("status") != "PLANNED":
            continue

        if "requested_end_ms" not in event:
            raise ValueError("planned semantic event requires requested_end_ms")
        decision = materialize_framing_decision(
            transition=transition,
            geometry_result=event_geometry,
            observations=observations,
            quality=quality,
            segment_id=str(event.get("segment_id", f"framing_{index:04d}")),
            requested_end_ms=int(event["requested_end_ms"]),
        )
        if is_hook:
            decision.derived["hook_scale_cap"] = HOOK_SCALE_CAP
            decision.derived["wide_boost_allowed"] = False
        framing.append(decision)
        current_state = decision.state
        current_scale = float(decision.derived.get("motion_end_scale", current_scale))

    content_edits = _content_edits(list(payload.get("content_edits") or []))
    framing = list(
        synthesize_source_base_coverage(
            content_edits=content_edits,
            framing_decisions=framing,
            observations=observations,
            quality=quality,
        )
    )
    provenance = {
        "planner_input_hash": sha256_canonical(payload),
        "geometry_output_hash": geometry["output_hash"],
        "framing_coverage_policy": "explicit_source_base_v1",
    }
    if hook_geometry is not None:
        provenance["hook_geometry_output_hash"] = hook_geometry["output_hash"]
        provenance["hook_scale_cap"] = HOOK_SCALE_CAP

    manifest = build_timeline_manifest(
        analysis_hash=str(geometry["analysis_hash"]),
        config_hash=str(geometry["config_hash"]),
        content_edits=content_edits,
        framing_decisions=framing,
        source_type=source_type,
        extra_provenance=provenance,
    )
    validation = validate_manifest_pre_render(manifest, quality=quality, pace=pace)
    return {
        "manifest": manifest,
        "decision_summary": tuple(decisions),
        "validation": validation,
    }
