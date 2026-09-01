from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProsodySample:
    t_ms: int
    pitch_z: float
    energy_z: float
    speech_rate_z: float = 0.0


@dataclass(frozen=True)
class ProsodyPeak:
    peak_id: str
    start_ms: int
    end_ms: int
    strength: float
    provenance: str = "deterministic_probe"


@dataclass(frozen=True)
class BreathInterval:
    breath_id: str
    start_ms: int
    end_ms: int
    confidence: float
    provenance: str = "deterministic_probe"


PROSODY_PEAK_Z = 1.5
BREATH_ENERGY_Z = -1.0
BREATH_PITCH_Z = -0.5
MERGE_GAP_MS = 200


def _merge_indices(samples: list[ProsodySample], indexes: list[int], gap_ms: int) -> list[list[int]]:
    groups: list[list[int]] = []
    for index in indexes:
        if not groups or samples[index].t_ms - samples[groups[-1][-1]].t_ms > gap_ms:
            groups.append([index])
        else:
            groups[-1].append(index)
    return groups


def detect_prosody_peaks(samples: list[ProsodySample]) -> tuple[ProsodyPeak, ...]:
    ordered = sorted(samples, key=lambda x: x.t_ms)
    indexes = [
        i for i, sample in enumerate(ordered)
        if max(sample.pitch_z, sample.energy_z) >= PROSODY_PEAK_Z
    ]
    peaks: list[ProsodyPeak] = []
    for group_index, group in enumerate(_merge_indices(ordered, indexes, MERGE_GAP_MS)):
        group_samples = [ordered[i] for i in group]
        peaks.append(
            ProsodyPeak(
                peak_id=f"pros_{group_index:04d}",
                start_ms=group_samples[0].t_ms,
                end_ms=group_samples[-1].t_ms,
                strength=round(max(max(x.pitch_z, x.energy_z) for x in group_samples), 6),
            )
        )
    return tuple(peaks)


def detect_breath_intervals(samples: list[ProsodySample]) -> tuple[BreathInterval, ...]:
    """Provisional acoustic breath candidates; output is evidence, not a hard gate."""
    ordered = sorted(samples, key=lambda x: x.t_ms)
    indexes = [
        i for i, sample in enumerate(ordered)
        if sample.energy_z <= BREATH_ENERGY_Z and sample.pitch_z <= BREATH_PITCH_Z
    ]
    breaths: list[BreathInterval] = []
    for group_index, group in enumerate(_merge_indices(ordered, indexes, MERGE_GAP_MS)):
        group_samples = [ordered[i] for i in group]
        depth = max(
            min(1.0, (-x.energy_z - 0.5) / 2.0)
            for x in group_samples
        )
        breaths.append(
            BreathInterval(
                breath_id=f"breath_{group_index:04d}",
                start_ms=group_samples[0].t_ms,
                end_ms=group_samples[-1].t_ms,
                confidence=round(max(0.0, depth), 6),
            )
        )
    return tuple(breaths)
