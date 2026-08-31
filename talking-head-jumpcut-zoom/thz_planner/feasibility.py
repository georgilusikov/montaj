from __future__ import annotations

from dataclasses import replace
from statistics import median
from typing import Iterable

from .schema import (
    CapResolution,
    CompositionMetrics,
    DesiredBand,
    FeasibilityInterval,
    FrameObservation,
    ShotState,
)

TOP_MARGIN_MIN = 0.05
BOTTOM_MARGIN_MIN = 0.02
SIDE_MARGIN_MIN = 0.02


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _crop_for_observation(obs: FrameObservation, scale: float) -> tuple[float, float, float, float]:
    """Return normalized source crop x0,y0,x1,y1.

    X tracks face center but is clamped to source bounds. Y first protects 5% output
    headroom, then is clamped. This is planner geometry, not a renderer pixel crop.
    """
    crop_w = 1.0 / scale
    crop_h = 1.0 / scale

    x0 = obs.face_cx - crop_w / 2.0
    x0 = max(0.0, min(1.0 - crop_w, x0))

    required_src_headroom = TOP_MARGIN_MIN / scale
    y0 = obs.hair_top - required_src_headroom
    y0 = max(0.0, min(1.0 - crop_h, y0))
    return x0, y0, x0 + crop_w, y0 + crop_h


def crop_for_observation(obs: FrameObservation, scale: float) -> tuple[float, float, float, float]:
    """Public deterministic normalized crop helper used by the planner only."""
    return _crop_for_observation(obs, scale)


def _measure(obs: FrameObservation, scale: float) -> tuple[float, float, float, float, float, float, float, tuple[str, ...]]:
    x0, y0, x1, y1 = _crop_for_observation(obs, scale)
    # Provisional face-width approximation until analysis emits a tracked face width.
    face_w = obs.face_ratio * 0.75
    face_left = obs.face_cx - face_w / 2.0
    face_right = obs.face_cx + face_w / 2.0

    top = (obs.hair_top - y0) * scale
    bottom = (y1 - obs.bottom_keep_y) * scale
    left = (face_left - x0) * scale
    right = (x1 - face_right) * scale
    face_center_x_out = (obs.face_cx - x0) * scale
    face_center_y_out = (obs.face_cy - y0) * scale

    caption_loss = 0.0
    reasons: list[str] = []
    if obs.caption_top is not None and obs.caption_bottom is not None:
        if obs.caption_top < y0 or obs.caption_bottom > y1:
            caption_loss = 1.0
            reasons.append("caption_clipped")

    if obs.gesture_hard_block:
        reasons.append("gesture_hard_block")
    if obs.prop_hard_block:
        reasons.append("prop_hard_block")
    if top < TOP_MARGIN_MIN:
        reasons.append("top_margin")
    if bottom < BOTTOM_MARGIN_MIN:
        reasons.append("bottom_margin")
    if left < SIDE_MARGIN_MIN:
        reasons.append("left_margin")
    if right < SIDE_MARGIN_MIN:
        reasons.append("right_margin")

    return (
        top,
        bottom,
        left,
        right,
        caption_loss,
        face_center_x_out,
        face_center_y_out,
        tuple(sorted(set(reasons))),
    )


def _window_safe(observations: list[FrameObservation], scale: float) -> tuple[bool, CompositionMetrics, tuple[str, ...]]:
    rows = [_measure(obs, scale) for obs in observations]
    reasons = tuple(sorted({r for row in rows for r in row[7]}))
    face = [obs.face_ratio * scale for obs in observations]
    metrics = CompositionMetrics(
        top_margin_min=min(r[0] for r in rows),
        bottom_margin_min=min(r[1] for r in rows),
        left_margin_min=min(r[2] for r in rows),
        right_margin_min=min(r[3] for r in rows),
        caption_overlap_max=max(r[4] for r in rows),
        face_ratio_p05=_quantile(face, 0.05),
        face_ratio_p50=_quantile(face, 0.50),
        face_ratio_p95=_quantile(face, 0.95),
        face_center_x_p50=_quantile([r[5] for r in rows], 0.50),
        face_center_y_p50=_quantile([r[6] for r in rows], 0.50),
        max_safe_scale=scale,
        limiting_reasons=reasons,
    )
    return not reasons, metrics, reasons


def _max_safe_scale(observations: list[FrameObservation], upper: float) -> tuple[float, CompositionMetrics, tuple[str, ...]]:
    upper = max(1.0, upper)
    safe_at_one, metrics_one, reasons_one = _window_safe(observations, 1.0)
    if not safe_at_one:
        return 1.0, metrics_one, reasons_one

    safe_upper, metrics_upper, reasons_upper = _window_safe(observations, upper)
    if safe_upper:
        return upper, metrics_upper, reasons_upper

    lo, hi = 1.0, upper
    for _ in range(24):
        mid = (lo + hi) / 2.0
        safe, _, _ = _window_safe(observations, mid)
        if safe:
            lo = mid
        else:
            hi = mid
    final_scale = round(lo, 6)
    _, metrics, reasons = _window_safe(observations, final_scale)
    return final_scale, metrics, reasons


def evaluate_window(
    observations: list[FrameObservation],
    band: DesiredBand,
    caps: CapResolution,
) -> FeasibilityInterval:
    if not observations:
        raise ValueError("window must contain observations")
    base_p50 = median(obs.face_ratio for obs in observations)
    desired_scale = max(1.0, band.face_target / max(base_p50, 1e-9))
    policy_upper = min(desired_scale, caps.quality_cap, caps.style_cap)
    geometry_cap, _, _ = _max_safe_scale(observations, policy_upper)
    actual_scale = min(policy_upper, geometry_cap)
    safe, metrics, reasons = _window_safe(observations, actual_scale)

    # Bands are desired targets, not universal hard lower bounds. Excessive p95
    # remains a hard safety failure; being below the desired target is allowed.
    hard_reasons = list(reasons)
    if metrics.face_ratio_p95 > band.face_max:
        hard_reasons.append("face_ratio_p95")
        safe = False

    return FeasibilityInterval(
        state=band.state,
        start_ms=min(o.t_ms for o in observations),
        end_ms=max(o.t_ms for o in observations),
        feasible=safe,
        desired_scale=round(desired_scale, 6),
        actual_scale=round(actual_scale, 6),
        metrics=metrics,
        hard_reasons=tuple(sorted(set(hard_reasons))),
    )


def build_temporal_feasibility_map(
    observations: Iterable[FrameObservation],
    bands: Iterable[DesiredBand],
    caps: CapResolution,
    *,
    window_ms: int = 500,
) -> dict[ShotState, list[FeasibilityInterval]]:
    obs = sorted(observations, key=lambda x: x.t_ms)
    if not obs:
        raise ValueError("observations required")
    if window_ms <= 0:
        raise ValueError("window_ms must be positive")

    start = obs[0].t_ms
    last_observed_ms = obs[-1].t_ms
    buckets: dict[int, list[FrameObservation]] = {}
    for item in obs:
        key = (item.t_ms - start) // window_ms
        buckets.setdefault(key, []).append(item)

    result: dict[ShotState, list[FeasibilityInterval]] = {}
    for band in bands:
        intervals: list[FeasibilityInterval] = []
        for key in sorted(buckets):
            interval = evaluate_window(buckets[key], band, caps)
            bucket_start = start + key * window_ms
            bucket_end = min(bucket_start + window_ms - 1, last_observed_ms)
            intervals.append(
                replace(interval, start_ms=bucket_start, end_ms=max(bucket_start, bucket_end))
            )
        result[band.state] = intervals
    return result
