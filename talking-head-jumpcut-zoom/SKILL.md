---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head Reels/Shorts/TikTok: pause cleanup from stable v1.7.5 core + semantic zooms with four Reels levels, 2–5 s framing rhythm, block continuity, accent targeting, guarded render and visual/pixel QC.'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

## Reels Four-Level Rhythm

This version is intentionally a **thin adapter over v1.7.5**, not a planner rewrite.
Read `SKILL_V1_7_5.md` for the unchanged production pipeline, pacing families,
visual scan, geometry, rendering and review requirements.

Use the normal v1.7.5 pipeline, replacing only:

```text
semantic_events.py -> semantic_events_v176.py
zoom_planner.py     -> zoom_planner_v176.py
```

`pipeline_guard.py` must see v1.7.6 semantic and zoom artifacts before render.

## Core ownership

```text
PACING     -> stable v1.7.5 speech_cleanup
SEMANTICS  -> WHY + block + accent + importance
CADENCE    -> low-level visual refresh only
SAFETY     -> may reduce or veto any crop
```

No new LLM pass, pause model, renderer, density controller or pipeline stage belongs
in v1.7.6.

## Four zoom levels

```text
HOME = 1.00
Z1   = 1.03   subtle refresh
Z2   = 1.06   light push / build
Z3   = 1.09   semantic punch
Z4   = 1.13   strong peak / payoff
```

`1.13` is the hard artistic maximum. Geometry/headroom/quality may reduce a target.
Safe fallbacks may therefore land slightly below its nominal level.

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

## Reels framing rhythm

Target rhythm:

```text
MIN_CHANGE_GAP       = 2.0 s
PREFERRED_CHANGE_GAP = 3.5 s
MAX_CHANGE_GAP       = 5.0 s
```

Interpretation:

- framing should normally not visibly change again inside ~2 s;
- ~3–4 s is the preferred Reels rhythm;
- after ~5 s without another visual change, cadence may add a low-level refresh;
- semantic framing and content jumpcuts reset the cadence clock;
- semantic framing has priority over cadence;
- if no safe boundary/crop exists, HOLD is valid.

Cadence may create only Z1/Z2. It can never create Z3 or Z4.

Very close semantic framing changes are coalesced instead of played as chatter. If two
candidate framing changes land inside 2 s, prefer one meaningful change; when one is
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

Do not recompute a tiny crop difference and call it a new zoom.

A HOME return that would be visible for less than ~2 s before the next framing change
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
For Reels, visible semantic framing has a minimum dwell of ~2 s so short semantic spans
do not create 0.5–1.2 s zoom flashes.

## Slow push

`slow_push` remains rare and explicit. It must reach the target and then settle:

```text
settle >= 300 ms
```

If there is not enough room for a meaningful transition plus settle, fall back to STEP.
Do not spend the entire episode moving and then immediately return HOME.

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
- configured 2.0 / 3.5 / 5.0 s window.

Do not add a hard per-level quota yet. Calibrate frequency from real gold Reels.

## QC / guard

v1.7.6 QC enforces:

```text
hard cap = 1.13
cadence max = Z2 / 1.06
Z1 <= 1.03
Z2 <= 1.06
Z3 <= 1.09
Z4 <= 1.13
framing gap >= ~2.0 s
slow_push settle >= 300 ms
```

`pipeline_guard.py` rejects mixing old semantic/zoom artifacts with the v1.7.6 run.
Actual visual review and post-render pixel QC remain mandatory exactly as in v1.7.5.

## Pause cleanup is intentionally unchanged

This PR does **not** implement the proposed per-gap semantic pause rewrite.
Family A/B/C and the v1.7.5 `speech_cleanup.py` remain unchanged so zoom/rhythm can be
validated independently on real videos.

## Explicit non-goals

Do not add now:

- rolling zoom-density controller;
- per-minute Z4 quota;
- visual-fatigue score inside semantic importance;
- new pause semantic pass;
- filler deletion;
- new RMS/VAD cutter;
- new renderer;
- new pipeline stage.

## Definition of Done

v1.7.6 is ready for real-video calibration when:

1. HOME/Z1/Z2/Z3/Z4 are bounded at `1.00/1.03/1.06/1.09/1.13`;
2. cadence creates only Z1/Z2;
3. Z4 requires raw strong semantics or explicit peak/ratchet_3;
4. important marks require WHY + block_id + accent_word;
5. safe boundary movement does not alter semantic duration;
6. same-block same-level events HOLD;
7. short HOME flashes and rapid framing chatter are suppressed;
8. normal visible framing rhythm is roughly 2–5 s, preferred ~3.5 s;
9. slow push has >=300 ms settle or falls back to STEP;
10. v1.7.5 geometry/headroom/visual/pixel QC remain intact;
11. pause cleanup behavior is unchanged in this version.
