from __future__ import annotations

from typing import Any

from .schema import (
    CanonicalCrop,
    FramingDecision,
    MotionIntent,
    RenderPrimitive,
    SCHEMA_VERSION,
    ShotState,
    sha256_canonical,
)
from .timeline import ContentEdit


def _crop(value: Any) -> CanonicalCrop:
    if not isinstance(value, dict):
        raise ValueError("canonical crop must be an object")
    return CanonicalCrop(
        x=int(value["x"]),
        y=int(value["y"]),
        w=int(value["w"]),
        h=int(value["h"]),
    )


def _content_edit(value: Any) -> ContentEdit:
    if not isinstance(value, dict):
        raise ValueError("content edit must be an object")
    return ContentEdit(
        segment_id=str(value["segment_id"]),
        src_start_ms=int(value["src_start_ms"]),
        src_end_ms=int(value["src_end_ms"]),
        out_start_ms=int(value["out_start_ms"]),
        out_end_ms=int(value["out_end_ms"]),
        transition_in=str(value.get("transition_in", "hard")),
        speech_impact=str(value.get("speech_impact", "none")),
    )


def _framing_decision(value: Any) -> FramingDecision:
    if not isinstance(value, dict):
        raise ValueError("framing decision must be an object")
    return FramingDecision(
        segment_id=str(value["segment_id"]),
        start_ms=int(value["start_ms"]),
        end_ms=int(value["end_ms"]),
        state=ShotState(str(value["state"])),
        motion_intent=MotionIntent(str(value["motion_intent"])),
        primitive=RenderPrimitive(str(value["primitive"])),
        crop_start=_crop(value["crop_start"]),
        crop_end=_crop(value["crop_end"]),
        anchor_policy=str(value["anchor_policy"]),
        time_basis=str(value.get("time_basis", "source")),
        why=dict(value.get("why") or {}),
        desired=dict(value.get("desired") or {}),
        can=dict(value.get("can") or {}),
        when=dict(value.get("when") or {}),
        derived=dict(value.get("derived") or {}),
        gates_passed=tuple(str(item) for item in (value.get("gates_passed") or ())),
        speech_impact=str(value.get("speech_impact", "none")),
    )


def verify_serialized_manifest_hash(payload: dict[str, Any]) -> str:
    """Verify the embedded hash against the canonical serialized payload.

    `manifest_hash` itself is excluded because `build_timeline_manifest` hashes the
    manifest immediately before adding that field.
    """
    embedded = str(payload.get("manifest_hash") or "")
    if len(embedded) != 64:
        raise ValueError("serialized manifest requires manifest_hash")
    unhashed = {key: value for key, value in payload.items() if key != "manifest_hash"}
    actual = sha256_canonical(unhashed)
    if actual != embedded.lower():
        raise ValueError("serialized manifest hash mismatch")
    return embedded.lower()


def parse_timeline_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse a canonical JSON manifest into renderer-facing typed objects."""
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object")
    if str(payload.get("schema_version")) != SCHEMA_VERSION:
        raise ValueError("unsupported manifest schema_version")
    manifest_hash = verify_serialized_manifest_hash(payload)

    content = tuple(_content_edit(item) for item in (payload.get("content_edits") or ()))
    framing = tuple(
        _framing_decision(item) for item in (payload.get("framing_decisions") or ())
    )
    return {
        "schema_version": str(payload["schema_version"]),
        "planner_version": str(payload["planner_version"]),
        "source_type": str(payload["source_type"]),
        "analysis_hash": str(payload["analysis_hash"]),
        "config_hash": str(payload["config_hash"]),
        "content_edits": content,
        "framing_decisions": framing,
        "provenance": dict(payload.get("provenance") or {}),
        "manifest_hash": manifest_hash,
    }


def manifest_from_planner_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept either a bare manifest or the `{manifest: ...}` planner CLI envelope."""
    candidate = payload.get("manifest") if isinstance(payload, dict) else None
    if candidate is None:
        candidate = payload
    if not isinstance(candidate, dict):
        raise ValueError("planner output does not contain a manifest object")
    return parse_timeline_manifest(candidate)
