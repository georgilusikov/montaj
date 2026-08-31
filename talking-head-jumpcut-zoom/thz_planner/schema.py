from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Iterable

SCHEMA_VERSION = "1.7.1"
FLOAT_DIGITS = 6


class ShotState(str, Enum):
    CONTEXT = "CONTEXT"
    ARGUMENT = "ARGUMENT"
    EMPHASIS = "EMPHASIS"


class MotionIntent(str, Enum):
    STATIC = "static"
    AMBIENT_DRIFT = "ambient_drift"
    SEMANTIC_PUSH = "semantic_push"
    SEMANTIC_PULL = "semantic_pull"


class RenderPrimitive(str, Enum):
    HOLD = "hold"
    STEP = "step"
    LINEAR_RAMP = "linear_ramp"


@dataclass(frozen=True)
class QualityMetrics:
    width: int
    height: int
    sharpness: float = 1.0       # normalized 0..1
    noise: float = 0.0           # normalized 0..1; higher is worse
    compression: float = 0.0     # normalized 0..1; higher is worse


@dataclass(frozen=True)
class FrameObservation:
    t_ms: int
    face_ratio: float
    face_cx: float               # normalized 0..1
    face_cy: float               # normalized 0..1
    hair_top: float              # normalized 0..1
    bottom_keep_y: float         # normalized 0..1; lowest must-keep subject/prop point
    caption_top: float | None = None
    caption_bottom: float | None = None
    gesture_hard_block: bool = False
    prop_hard_block: bool = False
    blur_hard_block: bool = False
    blink_hard_block: bool = False
    head_facing_camera: bool = True


@dataclass(frozen=True)
class DesiredBand:
    state: ShotState
    face_min: float
    face_max: float
    face_target: float


@dataclass(frozen=True)
class CapResolution:
    quality_cap_prior: float
    quality_cap: float
    style_cap: float
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositionMetrics:
    top_margin_min: float
    bottom_margin_min: float
    left_margin_min: float
    right_margin_min: float
    caption_overlap_max: float
    face_ratio_p05: float
    face_ratio_p50: float
    face_ratio_p95: float
    face_center_x_p50: float
    face_center_y_p50: float
    max_safe_scale: float
    limiting_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeasibilityInterval:
    state: ShotState
    start_ms: int
    end_ms: int
    feasible: bool
    desired_scale: float
    actual_scale: float
    metrics: CompositionMetrics
    hard_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeasibleShotState:
    state: ShotState
    scale: float
    face_ratio_p50: float
    face_center_x_p50: float
    face_center_y_p50: float
    composition_distance_from_previous: float | None
    limiting_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalCrop:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class FramingDecision:
    segment_id: str
    start_ms: int
    end_ms: int
    state: ShotState
    motion_intent: MotionIntent
    primitive: RenderPrimitive
    crop_start: CanonicalCrop
    crop_end: CanonicalCrop
    anchor_policy: str
    time_basis: str = "source"
    why: dict[str, Any] = field(default_factory=dict)
    desired: dict[str, Any] = field(default_factory=dict)
    can: dict[str, Any] = field(default_factory=dict)
    when: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, Any] = field(default_factory=dict)
    gates_passed: tuple[str, ...] = ()
    speech_impact: str = "none"


def _normalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    return value


def canonical_json(value: Any) -> str:
    """Byte-stable JSON for frozen planner inputs/outputs."""
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_candidate_sort(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic tie-break: score desc, semantic_fit desc, time asc, stable id asc."""
    return sorted(
        items,
        key=lambda x: (
            -round(float(x.get("score", 0.0)), FLOAT_DIGITS),
            -round(float(x.get("semantic_fit", 0.0)), FLOAT_DIGITS),
            int(x.get("ms", 0)),
            str(x.get("id", "")),
        ),
    )
