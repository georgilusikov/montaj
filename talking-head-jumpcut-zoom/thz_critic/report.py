from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Iterable

from .provenance import CriticProvenance, validate_provenance
from .registry import CheckRegistry, CheckResult

CRITIC_REPORT_SCHEMA_VERSION = "1.7.1"


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def canonical_report_json(value: Any) -> str:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_report_json(value).encode("utf-8")).hexdigest()


def build_critic_report(
    *,
    registry: CheckRegistry,
    results: Iterable[CheckResult],
    profile: str,
    provenance: CriticProvenance,
    features: set[str] | None = None,
    measurements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical critic report from independent measured results.

    A canonical v1.7.1 report requires explicit manifest binding. The mechanical
    result list is sorted by check id so report bytes are stable for frozen inputs.
    """
    validate_provenance(provenance, require_bound_inputs=True)
    ordered_results = tuple(sorted(results, key=lambda item: item.check_id))
    summary = registry.summarize(
        ordered_results,
        profile=profile,
        features=features,
    )

    report: dict[str, Any] = {
        "schema_version": CRITIC_REPORT_SCHEMA_VERSION,
        "producer": "thz_critic",
        "critic_version": provenance.critic_version,
        "profile": profile,
        "features": sorted(features or set()),
        "provenance": provenance,
        "checks": ordered_results,
        "measurements": measurements or {},
        "coverage": summary["coverage"],
        "pass_rate": summary["pass_rate"],
        "expected_ids": summary["expected_ids"],
        "missing_ids": summary["missing_ids"],
        "unknown_ids": summary["unknown_ids"],
        "required_failures": summary["required_failures"],
        "verdict": summary["verdict"],
    }
    report["report_hash"] = _sha256_canonical(report)
    return report
