# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

This is the compact engineering contract. `SKILL.md` is the canonical production-agent instruction.

## Architecture

v1.7.6 remains a thin evolution of the stable v1.7.5 pipeline:

```text
normalize -> Whisper -> speech_cleanup -> visual_scan
-> semantic_events_v176 -> zoom_planner_v176 -> QC/review -> render -> pixel/final QC
```

Geometry, renderer and visual evidence remain inherited from v1.7.5. v1.7.6 additionally tunes pause cleanup and Reels rhythm.

## Pause policy

Family A preserves timing by default.

Family B:

```text
cut_threshold_ms = 450
target_gap_ms     = 450
```

So pauses up to 450 ms remain intact and longer gaps are reduced to about 450 ms. Spoken words are never removed.

## Reels framing grammar

```text
HOME 1.00
Z1   1.03
Z2   1.06
Z3   1.09
Z4   1.13
HARD CAP 1.13
```

Cadence may use only Z1/Z2. Z3 is a semantic punch. Z4 is reserved for raw semantic importance >=0.90 or explicit `peak` / `ratchet_3`.

Performance remains a bounded amplifier (+0.08 max) but cannot create WHY or manufacture Z4 by itself.

## Rhythm

```text
minimum visible framing gap: ~3.0 s
preferred:                   ~4.5 s
maximum before soft refresh: ~6.0 s
```

Too-close semantic changes are coalesced; the stronger beat wins. A HOME return that would only flash briefly before the next framing change is suppressed.

## Semantic contract

For non-release events with raw importance >=0.40:

```text
WHY + block_id + accent_word are mandatory
```

Legacy fallbacks are allowed only with explicit `allow_legacy_semantic_defaults=true`.

`accent_word` owns the semantic target. Safe boundary selection may move WHEN but may not change `semantic_duration_ms`.

## Episode rules

```text
same block + same level -> HOLD
same block + escalation -> direct Z1/Z2 -> Z3 -> Z4 progression
new separated thought / release -> HOME when it can remain visible long enough
```

Visible semantic framing has a ~3 s dwell floor.

## Motion

STEP is the default.

Semantic `build` may automatically become a slow push:

```text
transition ~2.0 s
settle >=0.5 s
```

Peaks and cadence refreshes remain STEP unless explicitly overridden. If there is not enough room for the push plus settle, use STEP.

## Safety

The unchanged v1.7.5 core still enforces:

- Tripod Lock;
- global optical/eye-line anchor;
- face travel and crop safety;
- gesture/prop/caption protection;
- segment-wide >=5% headroom when hair evidence exists;
- blur/blink/pose/motion rejection;
- quality cap.

Safety can reduce or veto every requested zoom.

## Frequency

Do not hard-code a Z4-per-minute quota. `rhythm_summary` records Z1/Z2/Z3/Z4 counts, framing changes/minute, median gap and minimum gap for real-video calibration.

## Provenance

Production guard requires:

```text
semantic artifact: 1.7.6*
zoom plan:         1.7.6*
pre-QC:            1.7.6* when version is present
```

Visual scan remains the established 1.7.2-compatible perception stage.

## Intentionally deferred

- semantic/prosodic pause classification;
- rolling density controller;
- visual fatigue score;
- per-level frequency quota;
- new LLM pass;
- new renderer/pipeline stage.

Validate this calmer pacing/rhythm profile on real Reels before adding another system.
