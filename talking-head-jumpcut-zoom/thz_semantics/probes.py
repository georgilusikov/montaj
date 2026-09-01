from __future__ import annotations

import re
from typing import Iterable

from .schema import SalienceHit

_NUMBER_RE = re.compile(r"(?<!\w)(?:\d+[\d\s.,]*)(?:%|€|\$|₽|руб(?:лей|ля|ль)?|евро|доллар(?:ов|а)?)?(?!\w)", re.I)
_CURRENCY_RE = re.compile(r"(?:€|\$|₽|\b(?:руб(?:лей|ля|ль)?|евро|доллар(?:ов|а)?)\b)", re.I)
_PERCENT_RE = re.compile(r"(?:\d+[\d.,]*\s*%|\bпроцент(?:ов|а)?\b)", re.I)
_CONTRAST_RE = re.compile(r"\b(?:не\s+.{1,50}?\s+а\s+|но\s+на\s+самом\s+деле|instead|but\s+actually|not\s+.{1,40}?\s+but)\b", re.I)
_WARNING_RE = re.compile(r"\b(?:никогда|нельзя|опасн\w*|ошибк\w*|осторожн\w*|важно|never|must\s+not|warning|mistake|danger\w*)\b", re.I)
_NEGATION_RE = re.compile(r"\b(?:не|нет|ни|never|no|not)\b", re.I)
_SUMMARY_RE = re.compile(r"\b(?:итог|главн\w*|поэтому|значит|вывод|короче|the\s+point|bottom\s+line|therefore|so)\b", re.I)


def _weight(kind: str) -> float:
    return {
        "number": 0.50,
        "currency": 0.68,
        "percent": 0.65,
        "contrast": 0.78,
        "warning": 0.82,
        "negation": 0.45,
        "summary": 0.72,
    }[kind]


def _match_kinds(text: str) -> list[tuple[str, str]]:
    checks = (
        ("currency", _CURRENCY_RE),
        ("percent", _PERCENT_RE),
        ("contrast", _CONTRAST_RE),
        ("warning", _WARNING_RE),
        ("summary", _SUMMARY_RE),
        ("number", _NUMBER_RE),
        ("negation", _NEGATION_RE),
    )
    matches: list[tuple[str, str]] = []
    for kind, pattern in checks:
        found = pattern.search(text)
        if found:
            matches.append((kind, found.group(0).strip()))
    return matches


def detect_salience(segments: Iterable[dict[str, object]]) -> tuple[SalienceHit, ...]:
    """Deterministic multilingual lightweight salience probes.

    Input segments contain text/start_ms/end_ms. The probes emit evidence only;
    they do not choose a shot state, pattern, cut or scale.
    """
    hits: list[SalienceHit] = []
    for segment_index, segment in enumerate(segments):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start_ms = int(segment.get("start_ms", 0))
        end_ms = int(segment.get("end_ms", start_ms))
        if start_ms < 0 or end_ms < start_ms:
            raise ValueError("invalid transcript segment range")
        for match_index, (kind, evidence) in enumerate(_match_kinds(text)):
            hits.append(
                SalienceHit(
                    hit_id=f"sal_{segment_index:04d}_{match_index:02d}_{kind}",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    kind=kind,
                    weight=_weight(kind),
                    evidence=evidence,
                )
            )
    return tuple(sorted(hits, key=lambda h: (h.start_ms, h.end_ms, h.kind, h.hit_id)))
