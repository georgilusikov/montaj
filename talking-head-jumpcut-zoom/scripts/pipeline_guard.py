#!/usr/bin/env python3
"""Fail-closed production gate for the canonical Montaj pipeline.

Two stages are supported:
- pre-render: proves canonical pacing/family analysis + semantics + visual evidence exist.
- final: proves post-render pixel QC + final visual review exist before acceptance.

This does not replace human/agent judgment; it makes missing evidence explicit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

VERSION = "1.7.5-lite"


def _event_count(semantic: dict[str, Any]) -> int:
    return int(semantic.get("semantic_event_count", len(semantic.get("semantic_events", []) or [])))


def _reviewed_ids(receipt: dict[str, Any]) -> dict[str, str]:
    rows = receipt.get("reviewed_groups") or receipt.get("groups") or []
    result: dict[str, str] = {}
    for row in rows:
        group_id = str(row.get("id") or row.get("group_id") or "").strip()
        if group_id:
            result[group_id] = str(row.get("verdict") or row.get("status") or "").upper()
    return result


def _check_visual_review(
    manifest: dict[str, Any],
    receipt: dict[str, Any],
    errors: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    required = [str(x) for x in manifest.get("required_group_ids", [])]
    if not required:
        errors.append({"check": f"{label}_visual_manifest_empty"})
        return
    reviewer = str(receipt.get("reviewer") or receipt.get("review_method") or "").lower()
    if not any(token in reviewer for token in ("vision", "visual", "multimodal", "human")):
        errors.append({
            "check": f"{label}_visual_reviewer_missing",
            "reason": "receipt must identify a vision-capable or human reviewer",
        })
    reviewed = _reviewed_ids(receipt)
    missing = [group_id for group_id in required if group_id not in reviewed]
    rejected = [group_id for group_id in required if reviewed.get(group_id) not in {"PASS", "OK", "ACCEPT"}]
    if missing:
        errors.append({"check": f"{label}_visual_groups_missing", "group_ids": missing})
    if rejected:
        errors.append({"check": f"{label}_visual_groups_rejected", "group_ids": rejected})
    if str(receipt.get("status", "PASS")).upper() not in {"PASS", "OK", "ACCEPT"}:
        errors.append({"check": f"{label}_visual_receipt_failed"})


def _check_family_gate(cleanup: dict[str, Any], errors: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> tuple[str, bool]:
    family = str(cleanup.get("family") or "").upper()
    if family not in {"A", "B", "C"}:
        errors.append({"check": "family_gate_missing", "reason": "cleanup must record family A/B/C"})
        return family, bool(cleanup.get("pause_cleanup_enabled", False))

    metrics = cleanup.get("family_metrics")
    if not isinstance(metrics, dict) or not metrics.get("source"):
        errors.append({"check": "family_gate_provenance_missing"})

    cleanup_enabled = bool(cleanup.get("pause_cleanup_enabled", False))
    cuts = list(cleanup.get("content_cuts_ms") or [])
    cfg = dict(cleanup.get("config") or {})

    if family in {"A", "C"} and cuts and not cleanup_enabled:
        errors.append({"check": "dense_family_has_unexplained_content_cuts", "family": family})
    if family in {"A", "C"} and cleanup_enabled:
        warnings.append({
            "check": "dense_family_cleanup_override",
            "family": family,
            "reason": "A/C cleanup is allowed only as an explicit override; verify it was intentional",
        })
    if family == "B" and cleanup_enabled:
        threshold = int(cfg.get("cut_threshold_ms", 0) or 0)
        target = int(cfg.get("target_gap_ms", 0) or 0)
        if not 200 <= threshold <= 350:
            warnings.append({"check": "family_b_unusual_cut_threshold", "cut_threshold_ms": threshold})
        if not 120 <= target <= 240:
            warnings.append({"check": "family_b_unusual_target_gap", "target_gap_ms": target})

    return family, cleanup_enabled


def check_pre_render(
    cleanup: dict[str, Any],
    semantic: dict[str, Any],
    visual_scan: dict[str, Any],
    zoom_plan: dict[str, Any],
    pre_qc: dict[str, Any],
    visual_manifest: dict[str, Any],
    visual_review: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if not str(cleanup.get("version", "")).startswith("1.7"):
        errors.append({"check": "cleanup_provenance_missing"})
    if not cleanup.get("output_words"):
        errors.append({"check": "cleanup_output_words_missing"})
    if "content_cuts_ms" not in cleanup:
        errors.append({"check": "cleanup_content_cuts_missing"})
    family, cleanup_enabled = _check_family_gate(cleanup, errors, warnings)

    allow_no_semantics = bool((semantic.get("config") or {}).get("allow_no_semantic_events", False))
    if _event_count(semantic) <= 0 and not allow_no_semantics:
        errors.append({"check": "semantic_events_missing"})

    observations = visual_scan.get("observations") or []
    if not str(visual_scan.get("version", "")).startswith("1.7.2"):
        errors.append({"check": "visual_scan_provenance_missing"})
    if not observations:
        errors.append({"check": "visual_observations_missing"})
    coverage = float(visual_scan.get("face_coverage", 0.0) or 0.0)
    if coverage < 0.70:
        errors.append({"check": "visual_face_coverage_low", "face_coverage": coverage})

    allow_no_visible = bool((zoom_plan.get("config") or {}).get("allow_no_visible_framing", False))
    if not zoom_plan.get("decisions") and not allow_no_visible:
        errors.append({"check": "zoom_plan_decisions_missing"})
    if str(pre_qc.get("status", "")).upper() != "PASS":
        errors.append({"check": "pre_render_qc_not_pass"})

    if str(visual_manifest.get("phase", "pre")).lower() != "pre":
        errors.append({"check": "wrong_pre_visual_manifest_phase"})
    _check_visual_review(visual_manifest, visual_review, errors, label="pre")

    status = "PASS" if not errors else "FAIL"
    return {
        "version": VERSION,
        "stage": "pre-render",
        "status": status,
        "pipeline_lock": status,
        "visual_evidence": "PASS" if not any("visual" in e["check"] for e in errors) else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "evidence": {
            "family": family,
            "pause_cleanup_enabled": cleanup_enabled,
            "content_cut_count": len(cleanup.get("content_cuts_ms") or []),
            "semantic_event_count": _event_count(semantic),
            "visual_observation_count": len(observations),
            "face_coverage": coverage,
            "pre_qc_status": pre_qc.get("status"),
            "allow_no_visible_framing": allow_no_visible,
            "visual_review_group_count": len(visual_manifest.get("required_group_ids", [])),
        },
    }


def check_final(
    pre_guard: dict[str, Any],
    post_qc: dict[str, Any],
    visual_manifest: dict[str, Any],
    visual_review: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if str(pre_guard.get("status", "")).upper() != "PASS" or str(pre_guard.get("pipeline_lock", "")).upper() != "PASS":
        errors.append({"check": "pre_render_guard_not_pass"})
    if str(post_qc.get("status", "")).upper() != "PASS":
        errors.append({"check": "post_render_pixel_qc_not_pass"})
    if str(visual_manifest.get("phase", "")).lower() != "final":
        errors.append({"check": "wrong_final_visual_manifest_phase"})
    _check_visual_review(visual_manifest, visual_review, errors, label="final")
    status = "PASS" if not errors else "FAIL"
    return {
        "version": VERSION,
        "stage": "final",
        "status": status,
        "accepted_final": status == "PASS",
        "errors": errors,
        "evidence": {
            "pre_guard_status": pre_guard.get("status"),
            "post_qc_status": post_qc.get("status"),
            "verified_change_count": post_qc.get("verified_change_count"),
            "visual_review_group_count": len(visual_manifest.get("required_group_ids", [])),
        },
    }


def _read(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_or_print(report: dict[str, Any], output_json: str | None) -> int:
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if output_json:
        Path(output_json).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Montaj canonical pipeline guard")
    sub = parser.add_subparsers(dest="stage", required=True)

    pre = sub.add_parser("pre-render")
    pre.add_argument("--cleanup", required=True)
    pre.add_argument("--semantic", required=True)
    pre.add_argument("--visual-scan", required=True)
    pre.add_argument("--zoom-plan", required=True)
    pre.add_argument("--pre-qc", required=True)
    pre.add_argument("--visual-manifest", required=True)
    pre.add_argument("--visual-review", required=True)
    pre.add_argument("--output-json")

    final = sub.add_parser("final")
    final.add_argument("--pre-guard", required=True)
    final.add_argument("--post-qc", required=True)
    final.add_argument("--visual-manifest", required=True)
    final.add_argument("--visual-review", required=True)
    final.add_argument("--output-json")

    args = parser.parse_args(argv)
    if args.stage == "pre-render":
        report = check_pre_render(
            _read(args.cleanup),
            _read(args.semantic),
            _read(args.visual_scan),
            _read(args.zoom_plan),
            _read(args.pre_qc),
            _read(args.visual_manifest),
            _read(args.visual_review),
        )
        return _write_or_print(report, args.output_json)

    report = check_final(
        _read(args.pre_guard),
        _read(args.post_qc),
        _read(args.visual_manifest),
        _read(args.visual_review),
    )
    return _write_or_print(report, args.output_json)


if __name__ == "__main__":
    raise SystemExit(main())
