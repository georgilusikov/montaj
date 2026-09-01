# Talking-Head Jumpcut & Zoom Editor v1.7.5 Lite

This document is the compact engineering contract. `SKILL.md` is the production-agent instruction.

## Goal

Keep v1.7.2 fail-closed reliability while restoring restrained gold/early-v1.x directing:

```text
WHAT + bounded HOW -> editorial salience
```

Performance can amplify an existing semantic beat, but it cannot create WHY.

## Pipeline

```text
normalize_source.py
→ Whisper words
→ speech_cleanup.py [family gate A/B/C + pacing]
→ visual_scan.py
→ agent semantic_marks
→ semantic_events.py
→ analysis.json
→ zoom_planner.py
→ simple_qc.py
→ visual_evidence.py + real visual review
→ pipeline_guard.py pre-render
→ render_zoom.py
→ post_render_qc.py
→ final visual evidence/review
→ pipeline_guard.py final
```

## Pacing families

### A — dense

AUTO ambiguous → A. Default `pause_cleanup_enabled=false`.

### B — air

AUTO B requires repeated air:

```text
>=2 raw word gaps >450 ms
OR
>=4 raw word gaps >300 ms
```

Default:

```text
cut_threshold_ms=250
target_gap_ms=180
```

### C — explicit second take / CTA

Owner-supplied only. Body cleanup off by default.

`250 ms` is no longer a global default. Generic fail-safe default remains 500 ms, but canonical B explicitly resolves to 250 ms.

No ad-hoc RMS/VAD refinement is allowed until a canonical acoustic detector exists.

## Semantic contract

Required semantic mark:

```json
{
  "start_word": 10,
  "end_word": 15,
  "importance": 0.72,
  "why": "thesis payoff"
}
```

Optional performance fields:

```json
{
  "performance_emphasis": 0.9,
  "performance_evidence": "speaker leans in and delivery energy rises"
}
```

Rules:

- semantic importance `<0.40` gets no performance bonus;
- performance bonus max `+0.08`;
- performance evidence is required when performance_emphasis > 0;
- gaze/head movement alone is never WHY.

## Gold-lite framing

```text
CONTEXT    1.00
ARGUMENT   1.08
EMPHASIS   1.12
RATCHET_1  1.08
RATCHET_2  1.12
RATCHET_3  1.16
HARD CAP   1.20
```

Most runtime stays at CONTEXT.

Episode durations:

```text
micro_punch    0.5–1.2 s
beat           1.2–2.0 s
argument_hold  2.0–2.5 s rare
```

## Dramatic continuity

Do not force return-to-home between every adjacent semantic beat.

```text
same coherent thought:
1.00 → 1.08 build → 1.12 peak → 1.00 release
```

Reset to CONTEXT on a new block/release. A standalone compact punch normally returns home.

## Density

Observed gold density around one visible semantic punch per ~7 s is a **ceiling/warning**, never a target or quota.

```text
elapsed time ≠ WHY
```

Do not manufacture zooms to satisfy density.

## Safety

Boundary hard rejects:

- blink/eye closure;
- blur;
- unsafe head pose/turn;
- gesture/prop conflict;
- crop/headroom/face-travel violation.

Soft bonuses may include word boundary, pause, head return and cadence fit.

## Acceptance

A production result is accepted only after:

```text
pre-QC PASS
+ family provenance
+ machine visual observations
+ actual selected-frame review
+ guarded render
+ post-render pixel QC PASS
+ final visual review
+ final guard PASS
```

No canonical stage may be silently replaced by an agent-written production equivalent.
