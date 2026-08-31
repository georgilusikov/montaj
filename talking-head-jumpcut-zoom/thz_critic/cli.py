from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .provenance import build_bound_provenance, critic_package_sha256, sha256_file
from .registry import CheckRegistry, CheckResult
from .report import build_critic_report, canonical_report_json


def _check_results(items: list[dict[str, Any]]) -> list[CheckResult]:
    return [
        CheckResult(
            check_id=str(item["check_id"]),
            status=str(item["status"]),
            measured=(str(item["measured"]) if item.get("measured") is not None else None),
        )
        for item in items
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canonical v1.7.1 critic report producer")
    parser.add_argument("input", type=Path, help="Frozen independent critic input JSON")
    parser.add_argument("output", type=Path, help="Canonical critic report JSON")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    master_path = Path(payload["master_path"])
    if not master_path.is_file():
        raise ValueError("master_path does not exist")
    if payload.get("pass1_independent") is not True:
        raise ValueError("critic input must explicitly assert pass1_independent=true")

    provenance = build_bound_provenance(
        critic_version=str(payload["critic_version"]),
        script_sha256=critic_package_sha256(),
        master_sha256=sha256_file(master_path),
        manifest_sha256=str(payload["manifest_sha256"]),
        analysis_sha256=(
            str(payload["analysis_sha256"])
            if payload.get("analysis_sha256") is not None
            else None
        ),
        renderer_program_sha256=(
            str(payload["renderer_program_sha256"])
            if payload.get("renderer_program_sha256") is not None
            else None
        ),
        pass1_independent=True,
    )

    registry = CheckRegistry()
    report = build_critic_report(
        registry=registry,
        results=_check_results(list(payload.get("results") or [])),
        profile=str(payload["profile"]),
        provenance=provenance,
        features=set(payload.get("features") or []),
        measurements=dict(payload.get("measurements") or {}),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_report_json(report) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
