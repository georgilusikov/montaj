#!/usr/bin/env python3
"""
Strict Speech Cleanup & Jumpcut Planner (Phase 1) — v1.7.5 Lite.

The script owns the deterministic family gate and pause policy:
- Family A (dense): preserve timing; no pause compression by default.
- Family B (air): reduce clause gaps >250 ms to ~180 ms.
- Family C: explicit owner-supplied second-take/CTA case; body cleanup stays off.

Ambiguous AUTO classification fails safe to A. Explicit config can override the
family or pause_cleanup_enabled. Strict mode never removes spoken words.

The canonical contract is based on true word boundaries:
- head/tail padding is measured from the first/last spoken word;
- output words are remapped to the dense timeline with source-time provenance;
- acoustic/RMS/VAD refinement is NOT improvised here. Until a canonical acoustic
  boundary detector exists, word timings remain authoritative.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

VERSION = "1.7.5-lite"
CUT_THRESHOLD_DEFAULT_MS = 500  # fail-safe generic default, not Family-B policy
FAMILY_B_CUT_THRESHOLD_MS = 250
TARGET_GAP_DEFAULT_MS = 180
HEAD_PAD_DEFAULT_MS = 120
TAIL_PAD_DEFAULT_MS = 350
AUDIO_FADE_DEFAULT_MS = 15
WORD_PRE_PAD_MS = 40
WORD_POST_PAD_MS = 60


def _format_srt_time(ms: int) -> str:
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def export_srt(output_words: list[dict[str, Any]], srt_path: str | Path, max_words_per_card: int = 3) -> None:
    cards: list[tuple[int, int, str]] = []
    current_chunk: list[dict[str, Any]] = []

    for word in output_words:
        current_chunk.append(word)
        if len(current_chunk) >= max_words_per_card:
            start_ms = int(current_chunk[0]["start_ms"])
            end_ms = int(current_chunk[-1]["end_ms"])
            text = " ".join(item.get("text", "") for item in current_chunk).strip()
            cards.append((start_ms, max(start_ms + 250, end_ms), text))
            current_chunk = []

    if current_chunk:
        start_ms = int(current_chunk[0]["start_ms"])
        end_ms = int(current_chunk[-1]["end_ms"])
        text = " ".join(item.get("text", "") for item in current_chunk).strip()
        cards.append((start_ms, max(start_ms + 250, end_ms), text))

    lines: list[str] = []
    for idx, (start_ms, end_ms, text) in enumerate(cards, 1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(start_ms)} --> {_format_srt_time(end_ms)}")
        lines.append(text)
        lines.append("")

    Path(srt_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validated_words(raw_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = sorted((dict(w) for w in raw_words), key=lambda w: int(w["start_ms"]))
    prev_end = -1
    for index, word in enumerate(words):
        start = int(word["start_ms"])
        end = int(word["end_ms"])
        if start < 0 or end < start:
            raise ValueError(f"invalid word timing at index {index}: {start}..{end}")
        if start < prev_end:
            raise ValueError(f"overlapping/out-of-order words at index {index}")
        prev_end = end
    return words


def _raw_gap_metrics(words: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [
        max(0, int(words[i]["start_ms"]) - int(words[i - 1]["end_ms"]))
        for i in range(1, len(words))
    ]
    return {
        "gap_count": len(gaps),
        "gaps_over_250": sum(g > 250 for g in gaps),
        "gaps_over_300": sum(g > 300 for g in gaps),
        "gaps_over_450": sum(g > 450 for g in gaps),
        "max_gap_ms": max(gaps, default=0),
    }


def classify_family(words: list[dict[str, Any]], config: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Deterministic A/B/C family gate. Ambiguous AUTO -> A."""
    cfg = dict(config or {})
    explicit = str(cfg.get("family", "auto")).strip().upper()
    if explicit in {"A", "B", "C"}:
        metrics = _raw_gap_metrics(words)
        metrics.update({"source": "explicit", "ambiguous": False})
        return explicit, metrics
    if explicit not in {"", "AUTO"}:
        raise ValueError(f"invalid family: {explicit}; expected auto|A|B|C")

    metrics = _raw_gap_metrics(words)
    # Gold-derived conservative gate: B needs repeated air, not one isolated pause.
    is_b = metrics["gaps_over_450"] >= 2 or metrics["gaps_over_300"] >= 4
    family = "B" if is_b else "A"
    metrics.update({
        "source": "auto_raw_word_gaps",
        "ambiguous": not is_b and (metrics["gaps_over_450"] > 0 or metrics["gaps_over_300"] > 0),
        "rule": "B iff gaps>450ms >=2 OR gaps>300ms >=4; otherwise A",
    })
    return family, metrics


def _speech_blocks(words: list[dict[str, Any]], cut_threshold_ms: int) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    for word in words:
        start = int(word["start_ms"])
        end = int(word["end_ms"])
        if not blocks:
            blocks.append((start, end))
            continue
        prev_start, prev_end = blocks[-1]
        gap = start - prev_end
        if gap <= cut_threshold_ms:
            blocks[-1] = (prev_start, max(prev_end, end))
        else:
            blocks.append((start, end))
    return blocks


def _identity_plan(
    *,
    words: list[dict[str, Any]],
    duration_ms: int,
    config_out: dict[str, Any],
    family: str,
    family_metrics: dict[str, Any],
) -> dict[str, Any]:
    if duration_ms <= 0 and words:
        duration_ms = int(words[-1]["end_ms"])
    output_words = [
        {
            "text": w.get("text", ""),
            "start_ms": int(w["start_ms"]),
            "end_ms": int(w["end_ms"]),
            "source_start_ms": int(w["start_ms"]),
            "source_end_ms": int(w["end_ms"]),
            "src_start_ms": int(w["start_ms"]),
            "src_end_ms": int(w["end_ms"]),
        }
        for w in words
    ]
    return {
        "version": VERSION,
        "family": family,
        "family_metrics": family_metrics,
        "pause_cleanup_enabled": False,
        "source_duration_ms": duration_ms,
        "output_duration_ms": duration_ms,
        "config": config_out,
        "kept_segments": [{
            "id": "seg_000",
            "src_start_ms": 0,
            "src_end_ms": duration_ms,
            "out_start_ms": 0,
            "out_end_ms": duration_ms,
            "dur_ms": duration_ms,
        }],
        "removed_gaps": [],
        "content_cuts_ms": [],
        "output_words": output_words,
    }


def plan_cleanup(payload: dict[str, Any]) -> dict[str, Any]:
    source = dict(payload.get("source") or {})
    duration_ms = int(source.get("duration_ms", 0))

    config = dict(payload.get("config") or {})
    mode = str(config.get("mode", "strict")).lower()
    if mode != "strict":
        raise ValueError(f"Only strict mode is supported in Lite, got: {mode}")

    words = _validated_words(list(payload.get("words") or []))
    family, family_metrics = classify_family(words, config)

    explicit_threshold = "cut_threshold_ms" in config
    if "pause_cleanup_enabled" in config:
        pause_cleanup_enabled = bool(config["pause_cleanup_enabled"])
    else:
        pause_cleanup_enabled = family == "B" or explicit_threshold

    if family == "C" and "pause_cleanup_enabled" not in config:
        pause_cleanup_enabled = False

    if explicit_threshold:
        cut_threshold_ms = int(config["cut_threshold_ms"])
    elif family == "B":
        cut_threshold_ms = FAMILY_B_CUT_THRESHOLD_MS
    else:
        cut_threshold_ms = CUT_THRESHOLD_DEFAULT_MS

    target_gap_ms = max(0, int(config.get("target_gap_ms", TARGET_GAP_DEFAULT_MS)))
    head_pad_ms = max(0, int(config.get("head_pad_ms", HEAD_PAD_DEFAULT_MS)))
    tail_pad_ms = max(0, int(config.get("tail_pad_ms", TAIL_PAD_DEFAULT_MS)))
    audio_fade_ms = max(0, int(config.get("audio_fade_ms", AUDIO_FADE_DEFAULT_MS)))
    word_pre_pad_ms = max(0, int(config.get("word_pre_pad_ms", WORD_PRE_PAD_MS)))
    word_post_pad_ms = max(0, int(config.get("word_post_pad_ms", WORD_POST_PAD_MS)))

    config_out = {
        "mode": mode,
        "family": family,
        "pause_cleanup_enabled": pause_cleanup_enabled,
        "cut_threshold_ms": cut_threshold_ms,
        "target_gap_ms": target_gap_ms,
        "head_pad_ms": head_pad_ms,
        "tail_pad_ms": tail_pad_ms,
        "audio_fade_ms": audio_fade_ms,
        "word_pre_pad_ms": word_pre_pad_ms,
        "word_post_pad_ms": word_post_pad_ms,
        "acoustic_refinement": "disabled_until_canonical_detector",
    }

    if not words or not pause_cleanup_enabled:
        return _identity_plan(
            words=words,
            duration_ms=duration_ms,
            config_out=config_out,
            family=family,
            family_metrics=family_metrics,
        )

    blocks = _speech_blocks(words, cut_threshold_ms)

    kept_segments: list[dict[str, Any]] = []
    removed_gaps: list[dict[str, Any]] = []
    content_cuts_ms: list[int] = []
    out_cursor = 0
    left_gap = target_gap_ms // 2

    for idx, (block_start, block_end) in enumerate(blocks):
        if idx == 0:
            src_start = max(0, block_start - head_pad_ms)
        else:
            src_start = max(0, block_start - left_gap)

        if idx + 1 < len(blocks):
            next_start, _ = blocks[idx + 1]
            original_gap_ms = max(0, next_start - block_end)
            remaining_gap_ms = min(target_gap_ms, original_gap_ms)

            keep_before_next = min(left_gap, remaining_gap_ms)
            keep_after_current = remaining_gap_ms - keep_before_next
            src_end = block_end + keep_after_current

            removed_src_start = src_end
            removed_src_end = next_start - keep_before_next
            removed_ms = max(0, removed_src_end - removed_src_start)

            removed_gaps.append({
                "src_start_ms": removed_src_start,
                "src_end_ms": removed_src_end,
                "original_gap_ms": original_gap_ms,
                "remaining_gap_ms": remaining_gap_ms,
                "removed_ms": removed_ms,
                "dur_ms": removed_ms,
            })
        else:
            upper = duration_ms if duration_ms > 0 else block_end + tail_pad_ms
            src_end = min(upper, block_end + tail_pad_ms)

        seg_dur = max(0, src_end - src_start)
        if kept_segments:
            content_cuts_ms.append(out_cursor)

        kept_segments.append({
            "id": f"seg_{idx:03d}",
            "src_start_ms": src_start,
            "src_end_ms": src_end,
            "out_start_ms": out_cursor,
            "out_end_ms": out_cursor + seg_dur,
            "dur_ms": seg_dur,
        })
        out_cursor += seg_dur

    output_words: list[dict[str, Any]] = []
    for word in words:
        source_start = int(word["start_ms"])
        source_end = int(word["end_ms"])
        for seg in kept_segments:
            if seg["src_start_ms"] <= source_start and source_end <= seg["src_end_ms"]:
                offset = seg["out_start_ms"] - seg["src_start_ms"]
                output_words.append({
                    "text": word.get("text", ""),
                    "start_ms": source_start + offset,
                    "end_ms": source_end + offset,
                    "source_start_ms": source_start,
                    "source_end_ms": source_end,
                    "src_start_ms": source_start,
                    "src_end_ms": source_end,
                })
                break

    return {
        "version": VERSION,
        "family": family,
        "family_metrics": family_metrics,
        "pause_cleanup_enabled": True,
        "source_duration_ms": duration_ms,
        "output_duration_ms": out_cursor,
        "config": config_out,
        "kept_segments": kept_segments,
        "removed_gaps": removed_gaps,
        "content_cuts_ms": content_cuts_ms,
        "output_words": output_words,
    }


def render_cleanup(
    input_video: str | Path,
    plan: dict[str, Any],
    output_video: str | Path,
) -> None:
    kept = plan.get("kept_segments", [])
    if not kept:
        raise ValueError("No segments to keep in cleanup plan")

    # Identity Family-A/C plan should not pay a concat/re-encode penalty.
    if not plan.get("pause_cleanup_enabled", False) and len(kept) == 1:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_video),
            "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(output_video),
        ]
        subprocess.run(cmd, check=True)
        return

    fade_ms = int(plan.get("config", {}).get("audio_fade_ms", AUDIO_FADE_DEFAULT_MS))
    fade_s = fade_ms / 1000.0

    filter_complex_parts: list[str] = []
    concat_video_inputs: list[str] = []
    concat_audio_inputs: list[str] = []

    for i, seg in enumerate(kept):
        s_sec = seg["src_start_ms"] / 1000.0
        e_sec = seg["src_end_ms"] / 1000.0
        dur_sec = seg["dur_ms"] / 1000.0

        v_label = f"v{i}"
        a_label = f"a{i}"

        filter_complex_parts.append(
            f"[0:v]trim=start={s_sec:.3f}:end={e_sec:.3f},setpts=PTS-STARTPTS[{v_label}]"
        )
        filter_complex_parts.append(
            f"[0:a]atrim=start={s_sec:.3f}:end={e_sec:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:ss=0:d={fade_s:.3f},afade=t=out:st={max(0.0, dur_sec - fade_s):.3f}:d={fade_s:.3f}[{a_label}]"
        )
        concat_video_inputs.append(f"[{v_label}]")
        concat_audio_inputs.append(f"[{a_label}]")

    num_segs = len(kept)
    concat_in = "".join(f"{v}{a}" for v, a in zip(concat_video_inputs, concat_audio_inputs))
    filter_complex_parts.append(f"{concat_in}concat=n={num_segs}:v=1:a=1[outv][outa]")

    cmd = [
        "ffmpeg", "-y", "-i", str(input_video),
        "-filter_complex", ";".join(filter_complex_parts),
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output_video),
    ]
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Family-aware strict speech cleanup and jumpcut planning")
    parser.add_argument("input_json", help="Input speech JSON containing words and source info")
    parser.add_argument("output_json", help="Output cleanup plan JSON")
    parser.add_argument("--input-video", help="Optional raw video to render dense video")
    parser.add_argument("--output-video", help="Optional dense video output path")
    parser.add_argument("--export-srt", help="Optional output SRT subtitle path")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    cleanup_plan = plan_cleanup(payload)

    Path(args.output_json).write_text(
        json.dumps(cleanup_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.export_srt:
        export_srt(cleanup_plan["output_words"], args.export_srt)

    if args.input_video and args.output_video:
        render_cleanup(args.input_video, cleanup_plan, args.output_video)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
