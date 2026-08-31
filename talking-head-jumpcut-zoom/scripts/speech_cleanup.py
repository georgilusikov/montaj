#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_CUT_THRESHOLD_MS = 500
DEFAULT_TARGET_GAP_MS = 180
DEFAULT_HEAD_PAD_MS = 120
DEFAULT_TAIL_PAD_MS = 350
DEFAULT_AUDIO_FADE_MS = 15


def _word_start(word: dict[str, Any]) -> int:
    for key in ("start_ms", "start", "t0_ms"):
        if key in word:
            value = float(word[key])
            return int(round(value * 1000.0)) if key == "start" and value < 10000 else int(round(value))
    raise ValueError("word requires start_ms/start")


def _word_end(word: dict[str, Any]) -> int:
    for key in ("end_ms", "end", "t1_ms"):
        if key in word:
            value = float(word[key])
            return int(round(value * 1000.0)) if key == "end" and value < 10000 else int(round(value))
    raise ValueError("word requires end_ms/end")


def _normalize_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(words):
        start_ms = _word_start(raw)
        end_ms = _word_end(raw)
        if start_ms < 0 or end_ms <= start_ms:
            raise ValueError(f"invalid word timing at index {index}")
        normalized.append({**raw, "start_ms": start_ms, "end_ms": end_ms})
    normalized.sort(key=lambda item: (item["start_ms"], item["end_ms"]))
    previous_end = -1
    for index, word in enumerate(normalized):
        if word["start_ms"] < previous_end:
            raise ValueError(f"overlapping word timings at index {index}")
        previous_end = word["end_ms"]
    return normalized


def _output_segments(source_segments: list[tuple[int, int]]) -> tuple[list[dict[str, int]], list[int]]:
    out_cursor = 0
    kept: list[dict[str, int]] = []
    cuts: list[int] = []
    for index, (src_start, src_end) in enumerate(source_segments):
        duration = src_end - src_start
        if duration <= 0:
            continue
        out_start = out_cursor
        out_end = out_start + duration
        kept.append(
            {
                "segment_index": index,
                "src_start_ms": src_start,
                "src_end_ms": src_end,
                "out_start_ms": out_start,
                "out_end_ms": out_end,
            }
        )
        out_cursor = out_end
        if index > 0:
            cuts.append(out_start)
    return kept, cuts


def _remap_words(words: list[dict[str, Any]], kept: list[dict[str, int]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for word in words:
        match = next(
            (
                segment
                for segment in kept
                if segment["src_start_ms"] <= word["start_ms"]
                and word["end_ms"] <= segment["src_end_ms"]
            ),
            None,
        )
        if match is None:
            raise ValueError("word fell outside kept speech segment")
        output.append(
            {
                **word,
                "source_start_ms": word["start_ms"],
                "source_end_ms": word["end_ms"],
                "start_ms": match["out_start_ms"] + (word["start_ms"] - match["src_start_ms"]),
                "end_ms": match["out_start_ms"] + (word["end_ms"] - match["src_start_ms"]),
            }
        )
    return output


def plan_cleanup(payload: dict[str, Any]) -> dict[str, Any]:
    source = dict(payload.get("source") or {})
    duration_ms = int(source.get("duration_ms") or 0)
    words = _normalize_words(list(payload.get("words") or []))
    if not words:
        raise ValueError("speech cleanup requires word-level timings")
    if duration_ms <= 0:
        duration_ms = words[-1]["end_ms"] + DEFAULT_TAIL_PAD_MS

    config = dict(payload.get("config") or {})
    mode = str(config.get("mode", "strict"))
    if mode != "strict":
        raise ValueError("v1.7 Lite speech cleanup supports strict mode only")
    threshold = max(0, int(config.get("cut_threshold_ms", DEFAULT_CUT_THRESHOLD_MS)))
    target_gap = max(0, int(config.get("target_gap_ms", DEFAULT_TARGET_GAP_MS)))
    head_pad = max(0, int(config.get("head_pad_ms", DEFAULT_HEAD_PAD_MS)))
    tail_pad = max(0, int(config.get("tail_pad_ms", DEFAULT_TAIL_PAD_MS)))
    fade_ms = max(0, int(config.get("audio_fade_ms", DEFAULT_AUDIO_FADE_MS)))
    if target_gap >= threshold:
        raise ValueError("target_gap_ms must be smaller than cut_threshold_ms")

    half_left = target_gap // 2
    half_right = target_gap - half_left
    segment_start = max(0, words[0]["start_ms"] - head_pad)
    segments: list[tuple[int, int]] = []
    removed: list[dict[str, int]] = []

    for previous, current in zip(words, words[1:]):
        gap_start = int(previous["end_ms"])
        gap_end = int(current["start_ms"])
        gap_ms = gap_end - gap_start
        if gap_ms <= threshold:
            continue

        left_end = min(duration_ms, gap_start + half_left)
        right_start = max(0, gap_end - half_right)
        if left_end > segment_start:
            segments.append((segment_start, left_end))
        if right_start > left_end:
            removed.append(
                {
                    "src_start_ms": left_end,
                    "src_end_ms": right_start,
                    "removed_ms": right_start - left_end,
                    "original_gap_ms": gap_ms,
                    "remaining_gap_ms": gap_ms - (right_start - left_end),
                }
            )
        segment_start = right_start

    final_end = min(duration_ms, words[-1]["end_ms"] + tail_pad)
    if final_end > segment_start:
        segments.append((segment_start, final_end))

    merged: list[tuple[int, int]] = []
    for start, end in segments:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    kept, cuts = _output_segments(merged)
    output_words = _remap_words(words, kept)
    output_duration_ms = kept[-1]["out_end_ms"] if kept else 0
    removed_ms = duration_ms - output_duration_ms

    return {
        "version": "1.7-lite",
        "mode": "strict",
        "source_duration_ms": duration_ms,
        "output_duration_ms": output_duration_ms,
        "removed_duration_ms": removed_ms,
        "config": {
            "cut_threshold_ms": threshold,
            "target_gap_ms": target_gap,
            "head_pad_ms": head_pad,
            "tail_pad_ms": tail_pad,
            "audio_fade_ms": fade_ms,
        },
        "kept_segments": kept,
        "content_cuts_ms": cuts,
        "removed_gaps": removed,
        "output_words": output_words,
    }


def _seconds(ms: int) -> str:
    return f"{ms / 1000.0:.6f}"


def render_cleanup(input_path: str | Path, output_path: str | Path, plan: dict[str, Any]) -> None:
    segments = list(plan.get("kept_segments") or [])
    if not segments:
        raise ValueError("cleanup plan contains no kept segments")
    fade_ms = int((plan.get("config") or {}).get("audio_fade_ms", DEFAULT_AUDIO_FADE_MS))

    filters: list[str] = []
    concat_inputs: list[str] = []
    for index, segment in enumerate(segments):
        start_ms = int(segment["src_start_ms"])
        end_ms = int(segment["src_end_ms"])
        duration_ms = end_ms - start_ms
        if duration_ms <= 0:
            raise ValueError("kept segment duration must be positive")
        fade = min(fade_ms, max(0, duration_ms // 4))
        vlabel = f"v{index}"
        alabel = f"a{index}"
        filters.append(
            f"[0:v]trim=start={_seconds(start_ms)}:end={_seconds(end_ms)},setpts=PTS-STARTPTS[{vlabel}]"
        )
        audio_chain = (
            f"[0:a]atrim=start={_seconds(start_ms)}:end={_seconds(end_ms)},asetpts=PTS-STARTPTS"
        )
        if fade > 0:
            audio_chain += (
                f",afade=t=in:st=0:d={_seconds(fade)},"
                f"afade=t=out:st={_seconds(max(0, duration_ms - fade))}:d={_seconds(fade)}"
            )
        audio_chain += f"[{alabel}]"
        filters.append(audio_chain)
        concat_inputs.append(f"[{vlabel}][{alabel}]")

    filters.append("".join(concat_inputs) + f"concat=n={len(segments)}:v=1:a=1[vout][aout]")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(input_path),
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Montaj v1.7 Lite strict speech pause cleanup")
    parser.add_argument("input_json", help="JSON with source.duration_ms and word-level timings")
    parser.add_argument("output_plan_json")
    parser.add_argument("--input-video")
    parser.add_argument("--output-video")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    result = plan_cleanup(payload)
    Path(args.output_plan_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if bool(args.input_video) != bool(args.output_video):
        raise SystemExit("--input-video and --output-video must be provided together")
    if args.input_video and args.output_video:
        render_cleanup(args.input_video, args.output_video, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
