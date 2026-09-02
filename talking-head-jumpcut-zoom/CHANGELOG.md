# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.6-lite] - 2026-09-02

### Added
- Required semantic episode fields for important non-release marks: `block_id` + `accent_word`; legacy defaults now require explicit compatibility config.
- Four Reels zoom levels above exact HOME: Z1 1.03, Z2 1.06, Z3 1.09, Z4 1.13.
- Reels cadence adapter with ~2.0 s minimum, ~3.5 s preferred, ~5.0 s maximum visual-gap target; cadence may create only Z1/Z2.
- Rapid-semantic-change coalescing and short-HOME-flash suppression.
- Slow-push settle requirement (`>=300 ms`) with STEP fallback.
- `rhythm_summary` diagnostics for per-level counts and framing gaps.
- Pipeline provenance lock for v1.7.6 semantic + zoom artifacts.

### Changed
- Z4 now requires raw semantic importance >=0.90 or explicit `peak` / `ratchet_3`; performance bonus alone may not manufacture the strongest close-up.
- Visible semantic framing has a ~2 s dwell floor even when the semantic span itself is shorter.
- Same block + same zoom level is an explicit HOLD rather than a geometry-dependent re-zoom.
- Pause cleanup remains intentionally on the unchanged v1.7.5 family policy for isolated zoom/rhythm validation.

### Fixed
- Closed the mismatch where the documented 2–5 s Reels rhythm applied only to cadence filler while semantic zoom returns could still flash after 0.5–1.2 s.
- Closed silent fallback of missing `block_id` / `accent_word` in normal v1.7.6 runs.
- Restored one canonical hard artistic cap of 1.13 across current docs and QC.

## [1.7.5-lite] - 2026-09-01

### Added
- Executable family A/B/C gate inside `speech_cleanup.py`; AUTO classification is deterministic and ambiguous footage fails safe to Family A.
- Bounded performance-aware salience in `semantic_events.py`: HOW may amplify an existing semantic mark by at most +0.08 importance and requires evidence; performance never creates WHY.
- Pipeline guard now requires family-gate provenance before production render.
- Regression tests for family fail-safe behavior, Family-B 250→180 cleanup, missing family provenance, and performance amplification boundaries.

### Changed
- Generic pause cleanup default is back to fail-safe 500 ms; Family B explicitly resolves to 250 ms. Family A/C skip pause compression by default.
- Gold-lite framing is made unambiguous: normal ARGUMENT 1.08, EMPHASIS 1.12, ratchet 1.08/1.12/1.13.
- `~1 punch / 7 s` is documented only as an observational density ceiling, never a quota or cadence target.
- Dramatic continuity is restored: adjacent build→peak beats in one thought may sustain tension instead of forcing repeated home-frame chatter.
- `V1_7_LITE.md` is replaced with a current v1.7.5 engineering contract instead of the stale v1.7.1 title/content.

### Removed
- The production instruction to improvise RMS/VAD tail trimming without a canonical acoustic detector. Word timings remain authoritative until a tested canonical detector exists.

### Fixed
- Closed the v1.7.4 mismatch where `family gate` existed in prose but the mandatory pipeline jumped directly to cleanup.
- Closed the v1.7.4 regression where global `CUT_THRESHOLD_DEFAULT_MS=250` could overcut dense Family-A speech if the gate was skipped.
- Closed contradictory documentation around ARGUMENT 1.08 vs 1.10.

## [1.7.4-lite] - 2026-09-01

### Changed
- Family B pause default `cut_threshold_ms` **250** (`speech_cleanup.py`); `target_gap` still 180.
- Zoom gold-lite in planner: ARGUMENT cap 1.10, EMPHASIS/style moderate 1.12, ratchet 1.08/1.12/1.16; shorter episode bands.
- `SKILL.md` / `V1_7_LITE.md`: do not zoom setup/bridge; ~1 punch per 7 s; default peak 1.12 not 1.16; Whisper word-end tails may need RMS-auxiliary trim.

## [1.7.3-lite] - 2026-09-01

### Changed
- `SKILL.md` only (no Python): family gate A/B/C before pause cleanup; family B `cut_threshold` ~250–300 ms with `target_gap` 180 ms; gold-lite zoom (home majority, punch 1.06–1.10, strong 1.12–1.16, short episodes); hook/CTA default CONTEXT; WHY is thesis/payoff not bare numbers. Evidence: 1080p gold pairs 0712, 0814, 0818a, 0818b.

## [1.7.2-lite] - 2026-09-01

### Added
- `visual_scan.py`: executable dense-video perception pass. It samples the actual video and emits planner-ready face geometry, blur and optical-flow observations; MediaPipe FaceMesh is preferred when available with OpenCV Haar fallback.
- `visual_evidence.py`: deterministic extraction of frames around every content jumpcut, visible semantic reframe and return-to-context change for actual vision/human review.
- `pipeline_guard.py`: fail-closed pre-render and final acceptance gates that require canonical artifacts, machine visual observations, QC receipts and complete visual-review receipts.
- `test_pipeline_lock_and_visual_evidence.py`: regressions for transcript-only bypass, missing visual review, renderer guard validation and final visual acceptance.

### Changed
- `render_zoom.py` now requires a PASS `pipeline_guard.py pre-render` receipt in production; the explicit unsafe bypass is debug/unit-only. FFmpeg progress is exposed directly and the default x264 preset is `fast` rather than `medium`.
- `simple_qc.py` and `post_render_qc.py` can persist JSON receipts with `--output-json` for machine-verifiable pipeline provenance.
- `SKILL.md` now distinguishes machine perception from actual frame inspection and explicitly forbids claims that the video was visually checked based only on ffprobe/Whisper/RMS.
- `SKILL.md` forbids ad-hoc replacement production scripts (`run_full_montage.py`, custom planner/renderer, etc.) when a canonical stage exists.
- Caption export remains in scope, but inventing looped-PNG subtitle compositors inside a zoom run is explicitly out of scope unless a separate canonical subtitle renderer is requested/available.

### Fixed
- Closed the documentation-only `frame_defects/perception` gap: the pipeline now has a real canonical `video -> observations` stage.
- Closed the production bypass where an agent could read the skill, skip canonical stages, create its own montage script and still describe the result as a skill-compliant render.
- Closed the visual-evidence gap where transcript/audio analysis could be incorrectly described as watching the video.
- Preserved an explicit editorial no-zoom path while continuing to fail on silent/missing zoom execution.

## [1.7.1-lite] - 2026-09-01

### Added
- `semantic_events.py`: mandatory deterministic bridge from agent/LLM semantic WHY (`semantic_marks`) to dense-timeline `semantic_events` and word-boundary candidates.
- `post_render_qc.py`: pixel-level verification that `final.mp4` actually contains the crop/zoom declared in `zoom_plan.json`.
- `test_semantic_contract.py`: regression coverage for empty semantics, semantic no-op, deterministic word-index timing, explicit no-zoom override, and render-frame comparison helper.

### Changed
- `SKILL.md` now forbids direct `zoom_planner.py` execution before semantic marks and forbids ad-hoc replacement planners/build-analysis scripts during production runs.
- `simple_qc.py` is fail-closed for long edits: missing semantic decisions, zero visible framing changes, and ARGUMENT/EMPHASIS intent collapsing to no-op are errors.
- Acceptance now requires both pre-render plan QC and post-render pixel QC.

### Fixed
- Long talking-head videos can no longer silently render at a constant 100% crop and still receive QC PASS when semantic framing was expected.
- The previously implicit/missing `semantic_events` producer is now an explicit pipeline stage with a validated schema.

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
