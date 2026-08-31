from __future__ import annotations

from statistics import median

from .schema import CanonicalCrop, FrameObservation, QualityMetrics

TOP_MARGIN_OUT = 0.05
MAX_X_SHIFT_SRC = 0.04


def _even_floor(value: float) -> int:
    n = max(2, int(value))
    return n if n % 2 == 0 else n - 1


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def crop_dimensions(metrics: QualityMetrics, scale: float) -> tuple[int, int]:
    if scale < 1.0:
        raise ValueError("scale < 1.00 is not supported")
    w = _even_floor(metrics.width / scale)
    h = _even_floor(metrics.height / scale)
    return min(w, metrics.width), min(h, metrics.height)


def canonical_crop_at(
    *,
    observation: FrameObservation,
    metrics: QualityMetrics,
    scale: float,
    segment_hair_top: float,
) -> CanonicalCrop:
    """Deterministic renderer-facing crop.

    X follows the tracked face with the existing 4% source shift policy, but never
    beyond real crop freedom. Y uses segment-wide minimum hair top so headroom is
    protected for the whole selected window.
    """
    crop_w, crop_h = crop_dimensions(metrics, scale)
    centered_x = (metrics.width - crop_w) // 2
    max_crop_shift = (metrics.width - crop_w) // 2
    policy_shift = int(round(MAX_X_SHIFT_SRC * metrics.width))
    desired_shift = int(round((observation.face_cx - 0.5) * metrics.width))
    allowed_shift = min(policy_shift, max_crop_shift)
    x = centered_x + _clamp_int(desired_shift, -allowed_shift, allowed_shift)
    x = _clamp_int(x, 0, metrics.width - crop_w)

    required_headroom_src = (TOP_MARGIN_OUT * metrics.height) / scale
    y = int(round(segment_hair_top * metrics.height - required_headroom_src))
    y = _clamp_int(y, 0, metrics.height - crop_h)

    # ffmpeg-friendly even coordinates.
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
    segment_hair_top = min(o.hair_top for o in ordered)
    return (
        canonical_crop_at(
            observation=ordered[0],
            metrics=metrics,
            scale=start_scale,
            segment_hair_top=segment_hair_top,
        ),
        canonical_crop_at(
            observation=ordered[-1],
            metrics=metrics,
            scale=end_scale,
            segment_hair_top=segment_hair_top,
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
