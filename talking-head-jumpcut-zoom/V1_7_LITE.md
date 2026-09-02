# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

This is the compact engineering contract. `SKILL.md` is the canonical production-agent instruction.

## Architecture

v1.7.6 remains a thin Reels adapter over the stable v1.7.5 pipeline:

```text
normalize -> Whisper -> speech_cleanup v1.7.5 -> visual_scan
-> semantic_events_v176 -> zoom_planner_v176 -> QC/review -> render -> pixel/final QC
```

Pause cleanup, geometry, renderer and visual evidence are unchanged from v1.7.5.

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
minimum visible framing gap: ~2.0 s
preferred:                   ~3.5 s
maximum before soft refresh: ~5.0 s
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

Visible semantic framing has a ~2 s dwell floor to prevent short 0.5–1.2 s zoom flashes.

## Slow push

Slow push must leave at least 300 ms settled on the target. If there is no room, use STEP.

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

Do not hard-code a Z4-per-minute quota. `rhythm_summary` records Z1/Z2/Z3/Z4 counts, framing changes/minute, median gap and minimum gap for gold-video calibration.

## Provenance

Production guard requires:

```text
semantic artifact: 1.7.6*
zoom plan:         1.7.6*
pre-QC:            1.7.6* when version is present
```

The unchanged pacing artifact may remain `1.7.5-lite`; visual scan remains the established 1.7.2-compatible perception stage.

## Intentionally deferred

- per-gap semantic pause rewrite;
- rolling density controller;
- visual fatigue score;
- per-level frequency quota;
- new LLM pass;
- new renderer/pipeline stage.

Validate this zoom/rhythm change on real Reels before adding another system.
