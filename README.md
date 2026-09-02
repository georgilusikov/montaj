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

Clean source → editorial-energy Reels framing → final vertical master.

- Four energy-directed zoom levels: `1.03 / 1.05 / 1.08 / 1.12`
- Mandatory safe opening motion in the first ~5 s; real semantics replace synthetic intro beats
- Editorial-energy curve drives rise / hold / fall / release; cadence is only a ~3–6 s guard rail
- Family-B pauses: preserve up to ~450 ms; longer gaps compress to about 450 ms
- Gradual energy rises may use an eased ~2 s slow push; peaks remain STEP
- Z4 / 1.12 remains semantic-only; generated energy cannot manufacture the strongest close-up
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