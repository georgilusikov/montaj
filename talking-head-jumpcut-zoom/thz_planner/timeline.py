from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .planner import PLANNER_VERSION
from .schema import FramingDecision, SCHEMA_VERSION, sha256_canonical


@dataclass(frozen=True)
class ContentEdit:
    segment_id: str
    src_start_ms: int
    src_end_ms: int
    out_start_ms: int
    out_end_ms: int
    transition_in: str = "hard"
    speech_impact: str = "none"


def validate_content_edits(edits: Iterable[ContentEdit]) -> tuple[ContentEdit, ...]:
    ordered = tuple(sorted(edits, key=lambda x: (x.out_start_ms, x.segment_id)))
    previous_out_end = -1
    for edit in ordered:
        if edit.src_start_ms < 0 or edit.out_start_ms < 0:
            raise ValueError("content edit timestamps must be non-negative")
        if edit.src_end_ms < edit.src_start_ms or edit.out_end_ms < edit.out_start_ms:
            raise ValueError("content edit end must be >= start")
        if edit.out_start_ms < previous_out_end:
            raise ValueError("content edits overlap on output timeline")
        previous_out_end = edit.out_end_ms
    return ordered


def build_timeline_manifest(
    *,
    analysis_hash: str,
    config_hash: str,
    content_edits: Iterable[ContentEdit],
    framing_decisions: Iterable[FramingDecision],
    source_type: str,
    extra_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical v1.7.1 manifest with content and framing as separate planes."""
    if source_type not in {"live", "ai_avatar"}:
        raise ValueError(f"unknown source_type: {source_type}")

    content = validate_content_edits(content_edits)
    framing = tuple(sorted(framing_decisions, key=lambda x: (x.start_ms, x.segment_id)))
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "planner_version": PLANNER_VERSION,
        "source_type": source_type,
        "analysis_hash": analysis_hash,
        "config_hash": config_hash,
        "content_edits": content,
        "framing_decisions": framing,
        "provenance": extra_provenance or {},
    }
    manifest["manifest_hash"] = sha256_canonical(manifest)
    return manifest
