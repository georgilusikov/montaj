from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    NO_GO = "no_go"


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    severity: Severity
    profiles: tuple[str, ...] = ("live", "ai_avatar")
    feature: str | None = None


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str  # pass|warn|fail|skip
    measured: str | None = None


CORE_CHECKS = (
    CheckSpec("ASR_DIFF", Severity.NO_GO),
    CheckSpec("SYNC", Severity.NO_GO),
    CheckSpec("COLORSPACE", Severity.NO_GO),
    CheckSpec("LOUDNESS", Severity.NO_GO),
    CheckSpec("STATIC_STRETCH", Severity.NO_GO),
    CheckSpec("FEASIBLE_SHOT_STATES", Severity.NO_GO),
    CheckSpec("COMPOSITION_SAFE", Severity.NO_GO),
    CheckSpec("MOTION_FIDELITY", Severity.NO_GO),
    CheckSpec("BREATH_GATE", Severity.WARN, profiles=("live",)),
    CheckSpec("AI_FORCED_CADENCE", Severity.NO_GO, profiles=("ai_avatar",)),
    CheckSpec("AI_ARTIFACT_ALIGNMENT", Severity.NO_GO, profiles=("ai_avatar",)),
)


class CheckRegistry:
    def __init__(self, specs: Iterable[CheckSpec] = CORE_CHECKS) -> None:
        self._specs = {spec.check_id: spec for spec in specs}
        if len(self._specs) != len(tuple(specs)):
            raise ValueError("duplicate check ids")

    def resolve(self, *, profile: str, features: set[str] | None = None) -> tuple[CheckSpec, ...]:
        features = features or set()
        selected = [
            spec
            for spec in self._specs.values()
            if profile in spec.profiles and (spec.feature is None or spec.feature in features)
        ]
        return tuple(sorted(selected, key=lambda s: s.check_id))

    def summarize(
        self,
        results: Iterable[CheckResult],
        *,
        profile: str,
        features: set[str] | None = None,
    ) -> dict[str, object]:
        expected = self.resolve(profile=profile, features=features)
        expected_by_id = {spec.check_id: spec for spec in expected}
        reported = {result.check_id: result for result in results}

        missing = sorted(set(expected_by_id) - set(reported))
        unknown = sorted(set(reported) - set(expected_by_id))
        applicable = [r for cid, r in reported.items() if cid in expected_by_id and r.status != "skip"]
        passed = [r for r in applicable if r.status == "pass"]

        required_failures = sorted(
            cid
            for cid, result in reported.items()
            if cid in expected_by_id
            and result.status == "fail"
            and expected_by_id[cid].severity is Severity.NO_GO
        )

        coverage = 1.0 if not expected else (len(expected) - len(missing)) / len(expected)
        pass_rate = 1.0 if not applicable else len(passed) / len(applicable)
        verdict = "NO_GO" if missing or required_failures else "GO"

        return {
            "expected_ids": sorted(expected_by_id),
            "missing_ids": missing,
            "unknown_ids": unknown,
            "coverage": round(coverage, 6),
            "pass_rate": round(pass_rate, 6),
            "required_failures": required_failures,
            "verdict": verdict,
        }
