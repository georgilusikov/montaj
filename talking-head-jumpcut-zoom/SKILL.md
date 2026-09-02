---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head Reels/Shorts/TikTok: conservative pause cleanup, semantic zooms with four levels, calmer 3–6 s framing rhythm, selective ~2 s slow pushes, block continuity, accent targeting, guarded render and visual/pixel QC.'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

## Calmer Reels Four-Level Rhythm

This remains a **thin evolution of v1.7.5**, not a planner rewrite.
Read `SKILL_V1_7_5.md` for the unchanged production pipeline, visual scan, geometry,
rendering and review requirements.

Use the normal pipeline, with the v1.7.6 components:

```text
speech_cleanup.py     -> calmer Family-B pause policy
semantic_events_v176.py
zoom_planner_v176.py
```

`pipeline_guard.py` must see v1.7.6 semantic and zoom artifacts before render.

## Core ownership

```text
PACING     -> conservative pause cleanup
SEMANTICS  -> WHY + block + accent + importance
CADENCE    -> low-level visual refresh only
MOTION     -> STEP by default; selected builds may use SLOW_PUSH
SAFETY     -> may reduce or veto any crop
```

No new LLM pass, renderer, density controller or pipeline stage belongs in v1.7.6.

## Pause cleanup

The previous 250 ms-style pacing felt too compressed in real footage.

Family A remains conservative and preserves timing by default.

Family B now uses:

```text
cut_threshold_ms = 450
target_gap_ms     = 450
```

Meaning:

- pauses `<= 450 ms` are preserved;
- pauses `> 450 ms` are shortened to about `450 ms`;
- spoken words are never removed;
- explicit config may still override threshold/target for experiments.

Family C remains explicit second-take/CTA mode with body cleanup off by default.

## Four zoom levels

```text
HOME = 1.00
Z1   = 1.03   subtle refresh
Z2   = 1.06   light push / build
Z3   = 1.09   semantic punch
Z4   = 1.13   strong peak / payoff
```

`1.13` is the hard artistic maximum. Geometry/headroom/quality may reduce a target.
Safe fallbacks may therefore land slightly below the nominal level.

## Semantic contract

For every non-release semantic framing mark with raw `importance >= 0.40`, require:

```json
{
  "start_word": 10,
  "end_word": 16,
  "accent_word": 14,
  "block_id": "argument_02",
  "importance": 0.76,
  "why": "main correction / payoff"
}
```

Rules:

- `block_id` = one coherent thought or escalation;
- `accent_word` = the word where visual emphasis should land;
- agent chooses the word, deterministic code chooses milliseconds and a safe boundary;
- missing `block_id` or `accent_word` is an error by default;
- old fallback behavior exists only with explicit `allow_legacy_semantic_defaults=true`.

## Level selection

Performance remains the existing bounded `+0.08` amplifier from v1.7.5.
It may strengthen an existing semantic event, but it cannot create WHY.

Default mapping:

```text
effective importance <0.55     -> Z1
effective importance 0.55–0.71 -> Z2
effective importance 0.72+     -> Z3
```

Z4 is intentionally stricter:

```text
raw semantic_importance >= 0.90
OR direction == peak
OR direction == ratchet_3
```

Therefore performance bonus alone can move Z1→Z2 or Z2→Z3, but cannot manufacture Z4.

Direction overrides:

```text
build / ratchet_1 -> Z2
ratchet_2         -> Z3
peak / ratchet_3  -> Z4
release           -> HOME
```

## Calmer framing rhythm

After real-video review, the earlier 2–5 s cadence was too busy.

New target:

```text
MIN_CHANGE_GAP       = 3.0 s
PREFERRED_CHANGE_GAP = 4.5 s
MAX_CHANGE_GAP       = 6.0 s
```

Interpretation:

- framing should normally not visibly change again inside ~3 s;
- ~4–5 s is the preferred rhythm;
- after ~6 s without another visual change, cadence may add a low-level refresh;
- semantic framing and content jumpcuts reset the cadence clock;
- semantic framing has priority over cadence;
- if no safe boundary/crop exists, HOLD is valid.

Cadence may create only Z1/Z2. It can never create Z3 or Z4.

Very close semantic framing changes are coalesced instead of played as chatter. If two
candidate framing changes land inside ~3 s, prefer one meaningful change; when one is
stronger, the stronger semantic beat wins.

## Episode continuity

Same `block_id` should develop without flashing HOME between beats.

Preferred:

```text
1.00 -> Z1/Z2 -> Z3 -> Z4 -> 1.00
```

Same block + same zoom level:

```text
HOLD current framing
```

A HOME return that would be visible for less than ~3 s before the next framing change
is suppressed.

## Accent and duration

`accent_word` maps to `accent_ms`; boundary candidates are centered around the accent.
Visual safety may move or veto the transition.

Keep two separate concepts:

```text
semantic_duration_ms = semantic span duration
visual dwell          = how long framing remains visible
```

A shifted safe boundary must never change `semantic_duration_ms`.
For the calmer Reels profile, visible semantic framing has a minimum dwell of ~3 s.

## Motion: STEP vs SLOW_PUSH

STEP remains the default for punches, peaks and cadence refreshes.

A semantic `build` may automatically use SLOW_PUSH so the camera eases from one
framing level toward the next instead of jumping instantly.

Preferred slow push:

```text
transition ~= 2.0 s
settle     >= 0.5 s
```

Examples:

```text
HOME 1.00 --2s push--> Z2 1.06 --settle--> hold
Z2 1.06    --2s push--> Z3 1.09 --settle--> hold
```

Do not make every zoom a slow push. `peak`, `ratchet` punch and cadence changes remain
STEP unless explicitly requested otherwise. If there is not enough room for a useful
slow push plus settle, fall back to STEP.

## Safety remains unchanged

The v1.7.5 core still owns:

- Tripod Lock / no per-frame face chasing;
- global optical and eye-line anchor;
- face-travel checks;
- gesture/prop/caption safety;
- segment-wide headroom;
- `>=5%` air above hair when evidence exists;
- blur/blink/pose/motion rejection;
- quality and crop bounds.

Safety may reduce or veto every requested level, including Z4.

## Diagnostics

`rhythm_summary` reports:

- visible framing changes;
- semantic vs cadence changes;
- Z1/Z2/Z3/Z4 counts;
- changes per minute;
- median framing gap;
- minimum framing gap;
- configured 3.0 / 4.5 / 6.0 s window.

Do not add a hard per-level quota yet. Calibrate frequency from real Reels.

## QC / guard

v1.7.6 QC enforces:

```text
hard cap = 1.13
cadence max = Z2 / 1.06
Z1 <= 1.03
Z2 <= 1.06
Z3 <= 1.09
Z4 <= 1.13
framing gap >= ~3.0 s
slow_push settle >= 500 ms
```

`pipeline_guard.py` rejects mixing old semantic/zoom artifacts with the v1.7.6 run.
