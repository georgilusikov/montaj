from __future__ import annotations

from typing import Any

from .caps import resolve_caps
from .feasibility import build_temporal_feasibility_map
from .schema import (
    DesiredBand,
    FrameObservation,
    QualityMetrics,
    SCHEMA_VERSION,
    ShotState,
    canonical_json,
    sha256_canonical,
)
from .shot_states import derive_distinct_states

PLANNER_VERSION = "1.7.1-dev.2"

DEFAULT_BANDS = (
    DesiredBand(ShotState.CONTEXT, 0.26, 0.34, 0.30),
    DesiredBand(ShotState.ARGUMENT, 0.31, 0.40, 0.355),
    DesiredBand(ShotState.EMPHASIS, 0.38, 0.44, 0.41),
)


def plan_geometry_core(
    *,
    observations: list[FrameObservation],
    quality: QualityMetrics,
    intensity: str,
    pace: str,
    wide_boost: bool = False,
    wide_boost_cap: float | None = None,
    window_ms: int = 500,
    bands: tuple[DesiredBand, ...] = DEFAULT_BANDS,
    config_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic P0 geometry core used before semantic decision planning."""
    if not observations:
        raise ValueError("observations required")

    caps = resolve_caps(
        quality,
        intensity,
        wide_boost=wide_boost,
        wide_boost_cap=wide_boost_cap,
    )
    fmap = build_temporal_feasibility_map(
        observations,
        bands,
        caps,
        window_ms=window_ms,
    )

    bucket_count = max(len(v) for v in fmap.values())
    windows: list[dict[str, Any]] = []
    for index in range(bucket_count):
        intervals = [
            fmap[state][index]
            for state in sorted(fmap, key=lambda s: s.value)
            if index < len(fmap[state])
        ]
        states = derive_distinct_states(intervals, pace=pace)
        windows.append(
            {
                "index": index,
                "start_ms": min(x.start_ms for x in intervals),
                "end_ms": max(x.end_ms for x in intervals),
                "intervals": intervals,
                "distinct_states": states,
            }
        )

    analysis_payload = {
        "quality": quality,
        "observations": observations,
    }
    config_payload = config_payload or {
        "intensity": intensity,
        "pace": pace,
        "wide_boost": wide_boost,
        "wide_boost_cap": wide_boost_cap,
        "window_ms": window_ms,
        "bands": bands,
    }

    result = {
        "schema_version": SCHEMA_VERSION,
        "planner_version": PLANNER_VERSION,
        "analysis_hash": sha256_canonical(analysis_payload),
        "config_hash": sha256_canonical(config_payload),
        "caps": caps,
        "windows": windows,
    }
    result["output_hash"] = sha256_canonical(result)
    return result


def render_geometry_result(result: dict[str, Any]) -> str:
    """Canonical byte-stable representation for fixtures and hashing."""
    return canonical_json(result)
