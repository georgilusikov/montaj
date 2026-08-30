# montaj

AI-powered video editing pipeline for talking-head content. Two agent skills that work as a pipeline: **retake selection → jumpcut zoom**.

## Skills

### 1. [multimodal-video-retakes-editor](multimodal-video-retakes-editor/)

Raw footage with multiple retakes → select best takes via multimodal AI inspection → assemble `clean_source`.

- Word-level ASR transcription (Whisper)
- Semantic block clustering & retake grouping
- Direct video inspection by multimodal model (`view_file`)
- Scoring rubric: completeness, diction, prosody, eye contact, acoustics
- Safe audio hygiene (no destructive spectral gating)
- Outputs `clean_source.mp4` + `takes_report.json`

### 2. [talking-head-jumpcut-zoom](talking-head-jumpcut-zoom/)

Clean source → adaptive retention zoom cuts → final vertical master.

- Eye-line dramaturgy & blink/blur/pose gates
- 3-step dynamic zoom (1.00x → 1.08x → 1.16x)
- Live speaker & AI-avatar profiles
- FFmpeg render with trust-but-verify QC
- Outputs final master + SRT captions

## Pipeline

```
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
- Multimodal AI agent with `view_file` support for video/audio

## License

MIT
