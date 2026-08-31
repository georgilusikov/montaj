from __future__ import annotations

from dataclasses import dataclass

# Deliberately no imports from thz_planner. Post-render acceptance must not reuse
# planner geometry code, otherwise the same bug could self-attest twice.


@dataclass(frozen=True)
class RenderedCompositionSample:
    t_ms: int
    top_margin: float
    bottom_margin: float
    left_margin: float
    right_margin: float
    caption_overlap: float
    crop_x: float
    crop_y: float
    crop_w: float
    crop_h: float


def composition_safe_report(
    samples: list[RenderedCompositionSample],
    *,
    top_min: float = 0.05,
    bottom_min: float = 0.02,
    side_min: float = 0.02,
) -> dict[str, object]:
    if not samples:
        raise ValueError("rendered composition samples required")
    measured = {
        "top_margin_min": min(s.top_margin for s in samples),
        "bottom_margin_min": min(s.bottom_margin for s in samples),
        "left_margin_min": min(s.left_margin for s in samples),
        "right_margin_min": min(s.right_margin for s in samples),
        "caption_overlap_max": max(s.caption_overlap for s in samples),
    }
    failures: list[str] = []
    if measured["top_margin_min"] < top_min:
        failures.append("top_margin")
    if measured["bottom_margin_min"] < bottom_min:
        failures.append("bottom_margin")
    if measured["left_margin_min"] < side_min:
        failures.append("left_margin")
    if measured["right_margin_min"] < side_min:
        failures.append("right_margin")
    if measured["caption_overlap_max"] > 0.0:
        failures.append("caption_overlap")
    return {
        "check_id": "COMPOSITION_SAFE",
        "status": "fail" if failures else "pass",
        "measured": measured,
        "failures": sorted(failures),
    }


def _crop_tuple(sample: RenderedCompositionSample) -> tuple[float, float, float, float]:
    return sample.crop_x, sample.crop_y, sample.crop_w, sample.crop_h


def _max_abs_delta(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def motion_fidelity_report(
    samples: list[RenderedCompositionSample],
    *,
    expected_start_crop: tuple[float, float, float, float],
    expected_end_crop: tuple[float, float, float, float],
    tolerance_px: float = 4.0,
) -> dict[str, object]:
    """Compare independent measured crop transforms to the manifest endpoints."""
    if not samples:
        raise ValueError("rendered motion samples required")
    ordered = sorted(samples, key=lambda s: s.t_ms)
    actual_start = _crop_tuple(ordered[0])
    actual_end = _crop_tuple(ordered[-1])
    start_error = _max_abs_delta(actual_start, expected_start_crop)
    end_error = _max_abs_delta(actual_end, expected_end_crop)
    max_error = max(start_error, end_error)
    return {
        "check_id": "MOTION_FIDELITY",
        "status": "pass" if max_error <= tolerance_px else "fail",
        "measured": {
            "start_error_px": round(start_error, 6),
            "end_error_px": round(end_error, 6),
            "max_error_px": round(max_error, 6),
            "tolerance_px": tolerance_px,
        },
    }
