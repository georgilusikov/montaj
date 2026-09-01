# Talking-Head Jumpcut & Zoom Editor

AI-agent skill for vertical talking-head editing with semantic framing, strict pause cleanup, machine visual perception, deterministic FFmpeg rendering and fail-closed visual/QC gates.

Current production contract: **v1.7.2 Lite**. `SKILL.md` is authoritative.

## Core idea

Three separate layers:

```text
CONTENT / PACING        speech cleanup + jumpcuts
SEMANTIC FRAMING        WHY-driven zoom/reframe planning
VISUAL EVIDENCE         machine scan + actual inspected frames
```

A visual refresh does not automatically justify a zoom.

## Canonical pipeline

```text
normalize_source.py
→ Whisper word timings
→ speech_cleanup.py → dense.mp4
→ visual_scan.py
→ agent semantic WHY
→ semantic_events.py
→ zoom_planner.py
→ simple_qc.py
→ visual_evidence.py (pre)
→ actual vision/human review
→ pipeline_guard.py pre-render
→ render_zoom.py
→ post_render_qc.py
→ visual_evidence.py (final)
→ actual vision/human review
→ pipeline_guard.py final
→ accepted final
```

Production rendering is locked: `render_zoom.py` requires a PASS pre-render guard receipt.

## Why visual scan and visual review are both needed

`ffprobe`, Whisper and silence analysis do not inspect the image.

- `visual_scan.py` samples the dense video and produces planner-ready observations such as face geometry, blur and optical-flow motion. MediaPipe FaceMesh is used when available; OpenCV Haar is the fallback.
- `visual_evidence.py` extracts real JPG frames around jumpcuts and framing changes. A vision-capable agent or human must open those images and produce a review receipt.

The skill must not claim that it "watched" or visually checked the video without such evidence.

## Production lock

When a canonical stage exists, an agent must use it. It must not invent production replacements such as `run_full_montage.py`, `fast_montage.py`, `segment_montage.py`, a new planner or a custom renderer merely because a canonical step is inconvenient or slow.

If a canonical step fails: diagnose/fix that stage and rerun. Do not silently bypass it.

The zoom skill may export SRT captions, but it does not invent a looped-PNG subtitle compositor unless a separate canonical subtitle renderer is explicitly part of the workflow.

## Requirements

- Python 3.10+
- ffmpeg / ffprobe
- OpenCV (`opencv-python`) for `visual_scan.py`
- optional MediaPipe for stronger face/eye/mouth observations
- Whisper-compatible ASR with word timestamps

## Render performance

The canonical renderer uses a single video decode/filter graph and defaults to `libx264 -preset fast` at CRF 17. FFmpeg progress is exposed directly; agents should use real `out_time` / `speed` data rather than estimate progress from output file size.

## Versioning

See `CHANGELOG.md`. `V1_7_LITE.md` documents the earlier v1.7/v1.7.1 design; current execution rules live in `SKILL.md`.

## License

MIT
