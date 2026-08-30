# Talking-Head Jumpcut & Zoom Editor

AI-powered auto-editor for vertical talking-head videos (9:16): adaptive zoom cuts, eye-line dramaturgy, live speaker & AI-avatar profiles, ffmpeg render pipeline with trust-but-verify QC.

## What it does

Automatically edits vertical talking-head videos by:
- **Analyzing** speech (Whisper ASR), eye contact, head pose, gestures, motion blur, and blinks
- **Deciding** where to place zoom transitions (1.00x → 1.08x → 1.16x) based on dramatic patterns and speaker behavior
- **Rendering** the final video with ffmpeg (crop, zoom, loudness normalization, optional grain/drift)
- **Verifying** the result with double transcription, independent critic, and a master QC checklist

## Profiles

| Profile | When to use | Key features |
|---|---|---|
| **Live Mobile Speaker** | Real person on camera | Eye-line dramaturgy, head-pose/gesture/blur gates, segment-wide headroom, micro-drift fallback |
| **AI-Avatar** | HeyGen, Synthesia, etc. | Artifact scoring, forced cadence cuts, grain + micro-drift anti-plastic FX, region-crop B-roll |

## Pipeline

```
project_config.json → Source Normalization → Analysis (analysis.json)
→ Timeline Assembly (timeline.json + edit_plan.md) → Pre-render Gates (§5)
→ FFmpeg Render → Master QC: Double Transcription + Independent Critic
→ critic_report.json: GO / NO_GO (max 2 fix iterations)
```

## Quick start

This is an AI agent skill (SKILL.md). To use it:

1. Copy `SKILL.md` to your AI agent's skills directory
2. Trigger with: "смонтируй говорящую голову", "talking head zoom", "сделай зумы как в рилс"
3. The skill will run a startup intake, analyze your video, and produce a timeline + rendered master

## Requirements

- **ffmpeg** ≥ 6.0 (with libx264, loudnorm, vidstab)
- **Python** ≥ 3.10 with: whisper, opencv-python, numpy
- Input: vertical 9:16 video (1080p, 1440p, or 4K)

## Versioning

This project uses semantic versioning. See [CHANGELOG.md](CHANGELOG.md) for the full history.

## License

MIT
