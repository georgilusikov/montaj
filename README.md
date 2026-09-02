# montaj

AI-powered video editing pipeline for talking-head content. Two agent skills that work as a pipeline: **retake selection → jumpcut zoom**.

## Skills

### 1. [multimodal-video-retakes-editor](multimodal-video-retakes-editor/)

Raw footage with multiple retakes → select best takes via multimodal AI inspection → assemble `clean_source`.

- Word-level ASR transcription (Whisper)
- Semantic block clustering & retake grouping
- Direct video inspection by multimodal AI
- Scoring rubric: completeness, diction, prosody, eye contact, acoustics
- Safe audio hygiene (no destructive spectral gating)
- Outputs `clean_source.mp4` + `takes_report.json`

### 2. [talking-head-jumpcut-zoom](talking-head-jumpcut-zoom/)

Clean source → Reels-oriented semantic framing + cadence refresh → final vertical master.

- Four zoom levels above exact HOME: `1.03 / 1.06 / 1.09 / 1.13`, hard cap `1.13`
- Reels framing rhythm: normally ~2–5 s between visible framing changes, preferred ~3.5 s
- Cadence may use only low levels Z1/Z2; strong Z3/Z4 remain semantic
- Semantic block continuity + accent-word targeting
- Eye-line / headroom / blink / blur / pose / crop-safety gates
- Guarded FFmpeg render with visual evidence and post-render pixel QC
- Outputs final master + SRT captions

## Pipeline

```text
Raw footage (multiple retakes)
  ↓
multimodal-video-retakes-editor
  → clean_source.mp4 + takes_report.json
  ↓
talking-head-jumpcut-zoom
  → final_master.mp4 + captions.srt
```

## Requirements

- **ffmpeg** ≥ 6.0 (libx264, loudnorm)
- **Python** ≥ 3.10: `whisper`, `opencv-python`, `numpy`, `parselmouth`, `librosa`
- Multimodal AI agent with video/audio inspection support

## License

MIT
