from __future__ import annotations

from statistics import median

from .schema import CanonicalCrop, FrameObservation, QualityMetrics

TOP_MARGIN_OUT = 0.05
BOTTOM_MARGIN_OUT = 0.02
SIDE_MARGIN_OUT = 0.02
MAX_X_SHIFT_SRC = 0.04


def _even_floor(value: float) -> int:
    n = max(2, int(value))
    return n if n % 2 == 0 else n - 1


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def crop_dimensions(metrics: QualityMetrics, scale: float) -> tuple[int, int]:
    if scale < 1.0:
        raise ValueError("scale < 1.00 is not supported")
    w = _even_floor(metrics.width / scale)
    h = _even_floor(metrics.height / scale)
    return min(w, metrics.width), min(h, metrics.height)


def solve_normalized_window_crop(
    observations: list[FrameObservation],
    scale: float,
) -> tuple[tuple[float, float, float, float], tuple[str, ...]]:
    """Solve one fixed normalized crop that protects the whole observation window.

    Temporal feasibility and canonical rendering must use the same anchoring model.
    X therefore does not independently recenter for every probe sample. We solve a
    single crop origin from the intersection of side-margin constraints, the 4%
    policy shift and source bounds. Y similarly protects segment-wide hair top,
    bottom must-keep content and caption hard zones.

    When no exact fixed solution exists, the closest bounded crop is still returned
    together with a reason code; feasibility treats those reason codes as hard.
    """
    if not observations:
        raise ValueError("observations required")
    if scale < 1.0:
        raise ValueError("scale < 1.00 is not supported")

    ordered = sorted(observations, key=lambda item: item.t_ms)
    crop_w = 1.0 / scale
    crop_h = 1.0 / scale
    reasons: list[str] = []

    side_src = SIDE_MARGIN_OUT / scale
    face_left = [item.face_cx - (item.face_ratio * 0.75) / 2.0 for item in ordered]
    face_right = [item.face_cx + (item.face_ratio * 0.75) / 2.0 for item in ordered]

    source_x_lo = 0.0
    source_x_hi = max(0.0, 1.0 - crop_w)
    centered_x = source_x_hi / 2.0
    policy_lo = max(source_x_lo, centered_x - MAX_X_SHIFT_SRC)
    policy_hi = min(source_x_hi, centered_x + MAX_X_SHIFT_SRC)
    margin_x_lo = max(right + side_src - crop_w for right in face_right)
    margin_x_hi = min(left - side_src for left in face_left)
    x_lo = max(source_x_lo, policy_lo, margin_x_lo)
    x_hi = min(source_x_hi, policy_hi, margin_x_hi)

    desired_shift = _clamp(median(item.face_cx for item in ordered) - 0.5, -MAX_X_SHIFT_SRC, MAX_X_SHIFT_SRC)
    desired_x = centered_x + desired_shift
    if x_lo <= x_hi:
        x0 = _clamp(desired_x, x_lo, x_hi)
    else:
        reasons.append("x_window_no_solution")
        x0 = _clamp(desired_x, policy_lo, policy_hi)

    top_src = TOP_MARGIN_OUT / scale
    bottom_src = BOTTOM_MARGIN_OUT / scale
    source_y_lo = 0.0
    source_y_hi = max(0.0, 1.0 - crop_h)
    y_lo = max(
        source_y_lo,
        max(item.bottom_keep_y + bottom_src - crop_h for item in ordered),
    )
    y_hi = min(
        source_y_hi,
        min(item.hair_top - top_src for item in ordered),
    )

    caption_bottoms = [item.caption_bottom for item in ordered if item.caption_bottom is not None]
    caption_tops = [item.caption_top for item in ordered if item.caption_top is not None]
    if caption_bottoms:
        y_lo = max(y_lo, max(float(value) - crop_h for value in caption_bottoms))
    if caption_tops:
        y_hi = min(y_hi, min(float(value) for value in caption_tops))

    desired_y = min(item.hair_top for item in ordered) - top_src
    if y_lo <= y_hi:
        y0 = _clamp(desired_y, y_lo, y_hi)
    else:
        reasons.append("y_window_no_solution")
        y0 = _clamp(desired_y, source_y_lo, source_y_hi)

    x0 = _clamp(x0, source_x_lo, source_x_hi)
    y0 = _clamp(y0, source_y_lo, source_y_hi)
    return (
        (x0, y0, x0 + crop_w, y0 + crop_h),
        tuple(sorted(set(reasons))),
    )


def canonical_crop_at(
    *,
    observation: FrameObservation,
    metrics: QualityMetrics,
    scale: float,
    segment_hair_top: float,
) -> CanonicalCrop:
    """Compatibility helper for a one-sample canonical crop."""
    adjusted = FrameObservation(
        **{
            **observation.__dict__,
            "hair_top": min(observation.hair_top, segment_hair_top),
        }
    )
    return canonical_crop_for_window(
        observations=[adjusted],
        metrics=metrics,
        scale=scale,
    )


def canonical_crop_for_window(
    *,
    observations: list[FrameObservation],
    metrics: QualityMetrics,
    scale: float,
) -> CanonicalCrop:
    """Renderer-facing even-pixel crop from the same window solver as CAN."""
    normalized, _ = solve_normalized_window_crop(observations, scale)
    x0, y0, _, _ = normalized
    crop_w, crop_h = crop_dimensions(metrics, scale)
    max_x = metrics.width - crop_w
    max_y = metrics.height - crop_h

    x = _clamp_int(int(round(x0 * metrics.width)), 0, max_x)
    y = _clamp_int(int(round(y0 * metrics.height)), 0, max_y)
    x -= x % 2
    y -= y % 2
    return CanonicalCrop(x=x, y=y, w=crop_w, h=crop_h)


def canonical_crop_pair(
    *,
    observations: list[FrameObservation],
    metrics: QualityMetrics,
    start_scale: float,
    end_scale: float,
) -> tuple[CanonicalCrop, CanonicalCrop]:
    if not observations:
        raise ValueError("observations required")
    ordered = sorted(observations, key=lambda x: x.t_ms)
    return (
        canonical_crop_for_window(
            observations=ordered,
            metrics=metrics,
            scale=start_scale,
        ),
        canonical_crop_for_window(
            observations=ordered,
            metrics=metrics,
            scale=end_scale,
        ),
    )


def derived_scale(metrics: QualityMetrics, crop: CanonicalCrop) -> float:
    """Diagnostic only. Crop remains the canonical renderer truth."""
    return round(min(metrics.width / crop.w, metrics.height / crop.h), 6)


def window_anchor(observations: list[FrameObservation]) -> tuple[float, float]:
    if not observations:
        raise ValueError("observations required")
    return (
        round(median(o.face_cx for o in observations), 6),
        round(median(o.face_cy for o in observations), 6),
    )
