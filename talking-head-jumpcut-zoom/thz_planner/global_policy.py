from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import FramingDecision, ShotState

HOME_RETURN_MAX_MS = 12000
CONTEXT_SHARE_MIN = {
    "calm": 0.40,
    "neutral": 0.35,
    "high": 0.30,
}
ARGUMENT_SHARE_MAX = 0.45
OUTRO_BREATH_TARGET_MS = {
    "calm": 3000,
    "neutral": 2000,
    "high": 1500,
}
STRONG_FINAL_THRESHOLD = 0.80
STRONG_FINAL_MIN_BREATH_MS = 1000


@dataclass(frozen=True)
class HomeReturnViolation:
    start_ms: int
    end_ms: int
    duration_ms: int
    reason: str


@dataclass(frozen=True)
class StateBalanceReport:
    pace: str
    total_ms: int
    context_share: float
    argument_share: float
    emphasis_share: float
    context_min: float
    argument_max: float
    info_flags: tuple[str, ...]


@dataclass(frozen=True)
class OutroBreathPolicy:
    pace: str
    target_ms: int
    required_min_ms: int
    strong_final: bool
    status: str | None = None
    actual_ms: int | None = None


def _duration(decision: FramingDecision) -> int:
    return max(0, int(decision.end_ms) - int(decision.start_ms))


def _is_home(decision: FramingDecision) -> bool:
    # Explicit source-base coverage is the visual home even when a naturally tight
    # source is diagnostically classified ARGUMENT/EMPHASIS at scale 1.00.
    return bool(decision.derived.get("coverage_generated")) or decision.state is ShotState.CONTEXT


def home_return_report(
    framing_decisions: Iterable[FramingDecision],
    *,
    max_ms: int = HOME_RETURN_MAX_MS,
) -> tuple[HomeReturnViolation, ...]:
    """Find non-home visual runs exceeding the global HOME_RETURN safety maximum."""
    if max_ms <= 0:
        raise ValueError("home return max_ms must be positive")
    ordered = tuple(sorted(framing_decisions, key=lambda item: (item.start_ms, item.segment_id)))
    violations: list[HomeReturnViolation] = []
    run_start: int | None = None
    run_end: int | None = None

    def flush() -> None:
        nonlocal run_start, run_end
        if run_start is not None and run_end is not None:
            duration = run_end - run_start
            if duration > max_ms:
                violations.append(
                    HomeReturnViolation(
                        start_ms=run_start,
                        end_ms=run_end,
                        duration_ms=duration,
                        reason="global_home_return_max_exceeded",
                    )
                )
        run_start = None
        run_end = None

    for decision in ordered:
        if _is_home(decision):
            flush()
            continue
        if run_start is None:
            run_start = decision.start_ms
            run_end = decision.end_ms
            continue
        if decision.start_ms > int(run_end):
            flush()
            run_start = decision.start_ms
            run_end = decision.end_ms
        else:
            run_end = max(int(run_end), decision.end_ms)
    flush()
    return tuple(violations)


def state_balance_report(
    framing_decisions: Iterable[FramingDecision],
    *,
    pace: str,
) -> StateBalanceReport:
    """Informational state-share prior; never a mechanical GO/NO_GO by itself."""
    if pace not in CONTEXT_SHARE_MIN:
        raise ValueError(f"unknown pace: {pace}")
    durations = {state: 0 for state in ShotState}
    total = 0
    for decision in framing_decisions:
        duration = _duration(decision)
        durations[decision.state] += duration
        total += duration

    def share(state: ShotState) -> float:
        return 0.0 if total == 0 else durations[state] / total

    context = share(ShotState.CONTEXT)
    argument = share(ShotState.ARGUMENT)
    emphasis = share(ShotState.EMPHASIS)
    flags: list[str] = []
    if context < CONTEXT_SHARE_MIN[pace]:
        flags.append("context_share_below_prior")
    if argument > ARGUMENT_SHARE_MAX:
        flags.append("argument_share_above_prior")

    return StateBalanceReport(
        pace=pace,
        total_ms=total,
        context_share=round(context, 6),
        argument_share=round(argument, 6),
        emphasis_share=round(emphasis, 6),
        context_min=CONTEXT_SHARE_MIN[pace],
        argument_max=ARGUMENT_SHARE_MAX,
        info_flags=tuple(flags),
    )


def outro_breath_policy(
    *,
    pace: str,
    final_semantic_weight: float,
    actual_ms: int | None = None,
) -> OutroBreathPolicy:
    """Warn-policy for final visual breath; strong final emphasis may use >=1s."""
    if pace not in OUTRO_BREATH_TARGET_MS:
        raise ValueError(f"unknown pace: {pace}")
    if actual_ms is not None and actual_ms < 0:
        raise ValueError("actual outro breath must be non-negative")
    weight = max(0.0, min(1.0, float(final_semantic_weight)))
    strong = weight >= STRONG_FINAL_THRESHOLD
    target = OUTRO_BREATH_TARGET_MS[pace]
    required = STRONG_FINAL_MIN_BREATH_MS if strong else target
    status = None if actual_ms is None else ("pass" if actual_ms >= required else "warn")
    return OutroBreathPolicy(
        pace=pace,
        target_ms=target,
        required_min_ms=required,
        strong_final=strong,
        status=status,
        actual_ms=actual_ms,
    )
