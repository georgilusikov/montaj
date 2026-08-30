# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2026-08-28

### Changed
- **Default ASR Engine**: explicitly set to Whisper `large-v3-turbo` + `Silero VAD` across schema, profile matrix (§8), and `analysis.json` (§9) for millisecond-precise pause detection and top-tier Russian speech recognition.

## [1.4.0] - 2026-08-27

### Added
- **§0 Startup Intake**: 6-question project config (`project_config.json`) with defaults; subtitles export_only mode for external tools like CapCut
- **§1 Source Normalization**: mandatory pre-pass (rotation, VFR→CFR, HDR→Rec.709 tonemap, yuv420p); all coordinates in normalized space
- **§3 hard cut vs reframe semantics**: two distinct event types with different cadence rules; anti-flicker ≥1.8s; no-op ban
- **§3 `continuous_then_away` gaze label**: new segment-level gaze classification
- **§2 Framing Targets**: adaptive plan selection by `face_h_out_ratio` (plan1: 0.26–0.34, plan2: 0.31–0.40, plan3: 0.38–0.48)
- **§2 X-clamp overflow rule**: sustained off-center speaker caps plan to ≤1.08x with EDL logging
- **§4 `segments` as primary contract**: each segment with `src_ms`, `out_ms`, `dur_ms`, `type`, `scale`, `transition_in/out`; `zooms` become derived render-helper
- **§4 New JSON blocks**: `source_normalization`, `captions` (export_only + SRT + word-timestamps), `micro_drift` (fallback for live)
- **§5 Conflict Resolution Policy**: 7-level priority hierarchy for gate conflicts
- **§5 New gates**: framing targets, X-clamp overflow, source normalization, clean speech rule, loudness chain presence
- **§6 Micro-drift fallback**: live profile allows 1.00→1.03 drift only when no safe cut exists for >5s
- **§9 `speech_events`**: filler/false_start/long_pause events for clean_speech mode
- **§9 `background_patches`**: static background regions for zoom verification by critic
- **§11 Background-based zoom verification**: template-matching static patches instead of face_h for accurate zoom measurement
- **§11 Captions check**: SRT integrity verification (timing, text match, card duration, hard cut proximity)
- **§11 New critic checks**: SYNC, COLORSPACE, CAPTIONS_SRT
- **§12 New QC items**: B (Rec.709, rotation, CFR, PTS), G (sync), I (captions export)
- **§13 Edit Decision Log**: machine-readable per-segment decisions with reason, gates_passed, speech_impact

### Changed
- **§3 Reframe-down rule**: only triggers on gaze away ≥1.0s (short aways ignored); hard cut on away start only by overflow >4.5s rule
- **§4 JSON version**: 1.3 → 1.4
- **§4 JSON example completely rewritten**: demonstrates hard/reframe, src≠out, no no-ops; passes all §5 gates
- **§5 Loudness gate**: pre-render now checks filtergraph presence only; numeric measurement moved to post-render §12 F
- **§5 Rhythm gate**: hard cut cadence 2.2–4.5/2.0–4.0; reframe ≥1.8s from any event; no-op banned
- **§8 Matrix**: added micro-drift and subtitles rows
- **Execution Order**: expanded from 10 to 13 steps (intake, normalization, captions export)

### Fixed
- JSON example no longer contains no-op event at 3900ms (away_breath lives inside seg_001 at 1.00x)
- `source` field in JSON example corrected to `raw_video_1080p.mp4` (was `raw_video_2160p.mp4`)

## [1.3.0] - 2026-08-27

### Added
- §§9-12: Trust-but-verify post-render pipeline (analysis.json, double transcription, independent critic, master QC checklist)
- Mermaid verification loop with NO_GO feedback (max 2 iterations)
- §5 marked as pre-render; new sections are post-render

### Changed
- Execution order expanded to 10 steps

## [1.2.0] - 2026-08-27

### Added
- Live Mobile Speaker profile with eye-line dramaturgy
- 10 point fixes: JSON example fix, generalized margin formula, resolution-aware scale cap, dynamic X-center clamp, rhythm gate, eye-line classifier params

## [1.1.0] - 2026-08-27

### Added
- AI-Avatar mode (artifact scoring, region-crop inserts, anti-plastic FX, TTS alignment)
- Dynamic headroom clamp
- JSON v1.1

## [1.0.0] - 2026-08-27

### Added
- Initial skill: 3-step zoom system, 4-act dramatic patterns, silence trimming, ffmpeg render pipeline
- Basic critic gate and quality checklist
