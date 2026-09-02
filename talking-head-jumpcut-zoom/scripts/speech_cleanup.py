#!/usr/bin/env python3
"""Strict family-aware speech cleanup for the talking-head pipeline.

Family A: preserve timing by default.
Family B: compress pauses longer than 250 ms to about 250 ms.
Family C: explicit second-take/CTA mode; body cleanup off by default.

Strict mode never removes spoken words. Word timings remain authoritative until a
canonical acoustic boundary detector is introduced.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

VERSION = "1.7.6-lite"
CUT_THRESHOLD_DEFAULT_MS = 500
FAMILY_B_CUT_THRESHOLD_MS = 250
TARGET_GAP_DEFAULT_MS = 250
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
    chunk: list[dict[str, Any]] = []
    for word in output_words:
        chunk.append(word)
        if len(chunk) >= max_words_per_card:
            start = int(chunk[0]["start_ms"])
            end = int(chunk[-1]["end_ms"])
            text = " ".join(str(x.get("text", "")) for x in chunk).strip()
            cards.append((start, max(start + 250, end), text))
            chunk = []
    if chunk:
        start = int(chunk[0]["start_ms"])
        end = int(chunk[-1]["end_ms"])
        text = " ".join(str(x.get("text", "")) for x in chunk).strip()
        cards.append((start, max(start + 250, end), text))

    lines: list[str] = []
    for i, (start, end, text) in enumerate(cards, 1):
        lines += [str(i), f"{_format_srt_time(start)} --> {_format_srt_time(end)}", text, ""]
    Path(srt_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validated_words(raw_words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    words = sorted((dict(w) for w in raw_words), key=lambda w: int(w["start_ms"]))
    prev_end = -1
    for i, word in enumerate(words):
        start, end = int(word["start_ms"]), int(word["end_ms"])
        if start < 0 or end < start:
            raise ValueError(f"invalid word timing at index {i}: {start}..{end}")
        if start < prev_end:
            raise ValueError(f"overlapping/out-of-order words at index {i}")
        prev_end = end
    return words


def _raw_gap_metrics(words: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [max(0, int(words[i]["start_ms"]) - int(words[i - 1]["end_ms"])) for i in range(1, len(words))]
    return {
        "gap_count": len(gaps),
        "gaps_over_250": sum(g > 250 for g in gaps),
        "gaps_over_300": sum(g > 300 for g in gaps),
        "gaps_over_450": sum(g > 450 for g in gaps),
        "max_gap_ms": max(gaps, default=0),
    }


def classify_family(words: list[dict[str, Any]], config: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    cfg = dict(config or {})
    explicit = str(cfg.get("family", "auto")).strip().upper()
    if explicit in {"A", "B", "C"}:
        metrics = _raw_gap_metrics(words)
        metrics.update({"source": "explicit", "ambiguous": False})
        return explicit, metrics
    if explicit not in {"", "AUTO"}:
        raise ValueError(f"invalid family: {explicit}; expected auto|A|B|C")

    metrics = _raw_gap_metrics(words)
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
        start, end = int(word["start_ms"]), int(word["end_ms"])
        if not blocks:
            blocks.append((start, end))
            continue
        prev_start, prev_end = blocks[-1]
        if start - prev_end <= cut_threshold_ms:
            blocks[-1] = (prev_start, max(prev_end, end))
        else:
            blocks.append((start, end))
    return blocks


def _identity_plan(*, words: list[dict[str, Any]], duration_ms: int, config_out: dict[str, Any], family: str, family_metrics: dict[str, Any]) -> dict[str, Any]:
    if duration_ms <= 0 and words:
        duration_ms = int(words[-1]["end_ms"])
    output_words = [{
        "text": w.get("text", ""),
        "start_ms": int(w["start_ms"]), "end_ms": int(w["end_ms"]),
        "source_start_ms": int(w["start_ms"]), "source_end_ms": int(w["end_ms"]),
        "src_start_ms": int(w["start_ms"]), "src_end_ms": int(w["end_ms"]),
    } for w in words]
    return {
        "version": VERSION,
        "family": family,
        "family_metrics": family_metrics,
        "pause_cleanup_enabled": False,
        "source_duration_ms": duration_ms,
        "output_duration_ms": duration_ms,
        "config": config_out,
        "kept_segments": [{"id": "seg_000", "src_start_ms": 0, "src_end_ms": duration_ms, "out_start_ms": 0, "out_end_ms": duration_ms, "dur_ms": duration_ms}],
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
        cleanup_enabled = bool(config["pause_cleanup_enabled"])
    else:
        cleanup_enabled = family == "B" or explicit_threshold
    if family == "C" and "pause_cleanup_enabled" not in config:
        cleanup_enabled = False

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
        "mode": mode, "family": family, "pause_cleanup_enabled": cleanup_enabled,
        "cut_threshold_ms": cut_threshold_ms, "target_gap_ms": target_gap_ms,
        "head_pad_ms": head_pad_ms, "tail_pad_ms": tail_pad_ms,
        "audio_fade_ms": audio_fade_ms, "word_pre_pad_ms": word_pre_pad_ms,
        "word_post_pad_ms": word_post_pad_ms,
        "acoustic_refinement": "disabled_until_canonical_detector",
    }

    if not words or not cleanup_enabled:
        return _identity_plan(words=words, duration_ms=duration_ms, config_out=config_out, family=family, family_metrics=family_metrics)

    blocks = _speech_blocks(words, cut_threshold_ms)
    kept_segments: list[dict[str, Any]] = []
    removed_gaps: list[dict[str, Any]] = []
    content_cuts_ms: list[int] = []
    out_cursor = 0
    left_gap = target_gap_ms // 2

    for idx, (block_start, block_end) in enumerate(blocks):
        src_start = max(0, block_start - head_pad_ms) if idx == 0 else max(0, block_start - left_gap)
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
                "src_start_ms": removed_src_start, "src_end_ms": removed_src_end,
                "original_gap_ms": original_gap_ms, "remaining_gap_ms": remaining_gap_ms,
                "removed_ms": removed_ms, "dur_ms": removed_ms,
            })
        else:
            upper = duration_ms if duration_ms > 0 else block_end + tail_pad_ms
            src_end = min(upper, block_end + tail_pad_ms)

        seg_dur = max(0, src_end - src_start)
        if kept_segments:
            content_cuts_ms.append(out_cursor)
        kept_segments.append({
            "id": f"seg_{idx:03d}", "src_start_ms": src_start, "src_end_ms": src_end,
            "out_start_ms": out_cursor, "out_end_ms": out_cursor + seg_dur, "dur_ms": seg_dur,
        })
        out_cursor += seg_dur

    output_words: list[dict[str, Any]] = []
    for word in words:
        source_start, source_end = int(word["start_ms"]), int(word["end_ms"])
        for seg in kept_segments:
            if seg["src_start_ms"] <= source_start and source_end <= seg["src_end_ms"]:
                offset = seg["out_start_ms"] - seg["src_start_ms"]
                output_words.append({
                    "text": word.get("text", ""),
                    "start_ms": source_start + offset, "end_ms": source_end + offset,
                    "source_start_ms": source_start, "source_end_ms": source_end,
                    "src_start_ms": source_start, "src_end_ms": source_end,
                })
                break

    return {
        "version": VERSION, "family": family, "family_metrics": family_metrics,
        "pause_cleanup_enabled": True, "source_duration_ms": duration_ms,
        "output_duration_ms": out_cursor, "config": config_out,
        "kept_segments": kept_segments, "removed_gaps": removed_gaps,
        "content_cuts_ms": content_cuts_ms, "output_words": output_words,
    }


def render_cleanup(input_video: str | Path, plan: dict[str, Any], output_video: str | Path) -> None:
    kept = plan.get("kept_segments", [])
    if not kept:
        raise ValueError("No segments to keep in cleanup plan")
    if not plan.get("pause_cleanup_enabled", False) and len(kept) == 1:
        subprocess.run(["ffmpeg", "-y", "-i", str(input_video), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(output_video)], check=True)
        return

    fade_s = int(plan.get("config", {}).get("audio_fade_ms", AUDIO_FADE_DEFAULT_MS)) / 1000.0
    filters: list[str] = []
    video_inputs: list[str] = []
    audio_inputs: list[str] = []
    for i, seg in enumerate(kept):
        s, e, dur = seg["src_start_ms"] / 1000.0, seg["src_end_ms"] / 1000.0, seg["dur_ms"] / 1000.0
        v, a = f"v{i}", f"a{i}"
        filters.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[{v}]")
        filters.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,afade=t=in:ss=0:d={fade_s:.3f},afade=t=out:st={max(0.0, dur - fade_s):.3f}:d={fade_s:.3f}[{a}]")
        video_inputs.append(f"[{v}]")
        audio_inputs.append(f"[{a}]")
    concat_in = "".join(f"{v}{a}" for v, a in zip(video_inputs, audio_inputs))
    filters.append(f"{concat_in}concat=n={len(kept)}:v=1:a=1[outv][outa]")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_video), "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-crf", "17", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output_video),
    ], check=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Family-aware strict speech cleanup and jumpcut planning")
    p.add_argument("input_json")
    p.add_argument("output_json")
    p.add_argument("--input-video")
    p.add_argument("--output-video")
    p.add_argument("--export-srt")
    args = p.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    plan = plan_cleanup(payload)
    Path(args.output_json).write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.export_srt:
        export_srt(plan["output_words"], args.export_srt)
    if args.input_video and args.output_video:
        render_cleanup(args.input_video, plan, args.output_video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
