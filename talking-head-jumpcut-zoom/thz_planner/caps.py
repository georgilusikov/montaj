from __future__ import annotations

from dataclasses import replace

from .schema import CapResolution, QualityMetrics

STYLE_CAPS = {
    "calm": 1.10,
    "moderate": 1.16,
    "dynamic": 1.20,
}


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def quality_cap_prior(width: int, height: int) -> float:
    """Upper-bound prior only; not a lossless guarantee."""
    short = min(width, height)
    if short >= 2160:
        return 1.60
    if short >= 1440:
        return 1.40
    return 1.25


def resolve_quality_cap(metrics: QualityMetrics) -> tuple[float, float, tuple[str, ...]]:
    prior = quality_cap_prior(metrics.width, metrics.height)
    sharpness = clamp(metrics.sharpness, 0.0, 1.0)
    noise = clamp(metrics.noise, 0.0, 1.0)
    compression = clamp(metrics.compression, 0.0, 1.0)

    # Provisional deterministic heuristic. It scales only the extra zoom above 1.00.
    quality_factor = clamp(
        0.75 + 0.25 * sharpness - 0.15 * noise - 0.10 * compression,
        0.55,
        1.0,
    )
    resolved = 1.0 + (prior - 1.0) * quality_factor

    reasons: list[str] = [f"resolution_prior:{prior:.2f}"]
    if sharpness < 0.65:
        reasons.append("sharpness_reduced_cap")
    if noise > 0.35:
        reasons.append("noise_reduced_cap")
    if compression > 0.35:
        reasons.append("compression_reduced_cap")
    return prior, round(resolved, 6), tuple(reasons)


def resolve_style_cap(
    intensity: str,
    *,
    wide_boost: bool = False,
    wide_boost_cap: float | None = None,
) -> tuple[float, tuple[str, ...]]:
    if intensity not in STYLE_CAPS:
        raise ValueError(f"unknown intensity: {intensity}")
    base = STYLE_CAPS[intensity]
    if not wide_boost:
        return base, (f"style:{intensity}",)
    boosted = max(base, wide_boost_cap if wide_boost_cap is not None else base)
    return round(boosted, 6), (f"style:{intensity}", "wide_boost")


def resolve_caps(
    metrics: QualityMetrics,
    intensity: str,
    *,
    wide_boost: bool = False,
    wide_boost_cap: float | None = None,
) -> CapResolution:
    prior, quality, q_reasons = resolve_quality_cap(metrics)
    style, s_reasons = resolve_style_cap(
        intensity,
        wide_boost=wide_boost,
        wide_boost_cap=wide_boost_cap,
    )
    return CapResolution(
        quality_cap_prior=prior,
        quality_cap=quality,
        style_cap=style,
        reason_codes=q_reasons + s_reasons,
    )
