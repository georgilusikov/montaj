---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head Reels/Shorts/TikTok: conservative pause cleanup, editorial-energy camera curve, guaranteed opening motion, four zoom levels, selective slow pushes, semantic continuity, guarded render and visual/pixel QC.'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.6 Energy

## Editorial Energy Director

This remains a **thin evolution of the stable v1.7.6 Reels adapter**, not a planner rewrite.
The existing v1.7.5/v1.7.6 geometry, visual safety, boundary selection, renderer and QC remain authoritative.

Use the normal pipeline with:

```text
speech_cleanup.py
semantic_events_v176.py
zoom_planner_energy_v176.py   <- canonical zoom entry point
```

`zoom_planner_energy_v176.py` wraps `zoom_planner_v176.py`; it does not add another LLM pass or render stage.

## Core ownership

```text
PACING      -> conservative pause cleanup
SEMANTICS   -> WHY + block + accent + semantic importance
ENERGY      -> camera trajectory: rise / hold / fall / release
CADENCE     -> guard rail only when the picture stays static too long
MOTION      -> STEP or selective SLOW_PUSH
SAFETY      -> may reduce or veto every requested crop
```

## Pause cleanup

Family A preserves timing by default.

Family B:

```text
cut_threshold_ms = 450
target_gap_ms     = 450
```

So pauses `<=450 ms` remain intact and longer pauses are shortened to about `450 ms`.
Spoken words are never removed.

## Four camera levels

The energy profile uses four ordered zoom levels above exact HOME:

```text
HOME = 1.00
Z1   = 1.03   subtle attention refresh
Z2   = 1.05   light build
Z3   = 1.08   semantic / energy punch
Z4   = 1.12   strong semantic peak / payoff
```

`1.12` is the profile artistic maximum. Existing geometry/headroom/quality checks may reduce it further.
Synthetic energy events may shape only Z1-Z3; they may never manufacture Z4.
Z4 still requires a real semantic peak (`raw semantic_importance >=0.90`, `peak`, or `ratchet_3`).

## Semantic contract

For every important non-release semantic mark (`raw importance >=0.40`):

```text
WHY + block_id + accent_word are mandatory
```

`block_id` groups one coherent thought. `accent_word` is the semantic target.
The agent owns WHY; deterministic code owns the exact safe millisecond and crop.

## Editorial energy

The director derives a lightweight `editorial_energy` value from the already available semantic importance, direction and bounded performance salience.
It does **not** claim to measure real viewer attention.

Think of the curve as:

```text
energy rising quickly  -> STEP punch
energy rising steadily -> SLOW_PUSH toward a higher level
energy roughly flat    -> HOLD / keep current framing
energy falling a little-> move to a lower zoom level
energy falling strongly-> release toward HOME
```

Small falls therefore do not force HOME every time. A sequence may naturally breathe:

```text
1.00 -> 1.03 -> 1.05 -> 1.08 -> 1.05 -> 1.03 -> 1.00
```

or continue upward when the argument builds:

```text
1.00 -> 1.03 -> 1.05 -> 1.08 -> 1.12
```

## Mandatory opening motion: first 5 seconds

The first five seconds must not remain visually dead.
The director tries to create a low-level rising intro ramp around:

```text
~0.8 s -> Z1 / 1.03
~3.9 s -> Z2 / 1.05
```

These are **targets, not blind timer cuts**. If a real semantic event exists nearby, it replaces the synthetic intro beat.
The opening ramp uses SLOW_PUSH when safe, so energy visibly builds instead of jumping randomly.

Visual safety remains higher priority. If no safe crop/boundary exists, the movement may be vetoed and must be reported by diagnostics rather than forced through a bad frame.

## After 5 seconds: energy first, cadence second

The old `3 / 4.5 / 6 s` rule is now a guard rail, not the reason for a zoom:

```text
<3.0 s   normally avoid another visible framing change
~4.5 s   useful checkpoint / preferred breathing interval
>6.0 s   if nothing meaningful happened, allow a low-level cadence refresh
```

The director inserts sparse energy checkpoints roughly every `4.5 s` only when there is no nearby real semantic event.
At each checkpoint it estimates the curve between surrounding semantic points:

- rising energy -> move closer;
- falling energy -> step down one level or release HOME;
- flat energy -> HOLD when the framing already fits;
- no future semantic energy -> gradually decay toward a calmer framing.

Existing cadence Z1/Z2 remains a final fallback for unusually long static gaps.

## Motion

STEP remains correct for sharp peaks/payoffs.
SLOW_PUSH is preferred for gradual energy rise and opening/build moments.

Target slow push:

```text
transition ~= 2.0 s
settle     >= 0.5 s
```

The renderer uses eased interpolation, so slow push accelerates/decelerates smoothly instead of moving linearly.
If there is not enough room for a useful push plus settle, fall back to STEP.

## Continuity

Same `block_id` should develop without HOME chatter.

```text
same block + same level -> HOLD
same block + rising energy -> progress directly upward
small energy fall -> lower level without mandatory HOME
large semantic release -> HOME
```

A short HOME flash before the next change is suppressed.

## Safety remains unchanged

The inherited planner still enforces:

- Tripod Lock / no per-frame face chasing;
- global optical and eye-line anchor;
- face-travel checks;
- gesture/prop/caption safety;
- segment-wide headroom;
- `>=5%` air above hair when evidence exists;
- blink/blur/pose/motion rejection;
- quality and crop bounds.

Safety may reduce or veto every energy request.

## Diagnostics

The zoom plan must expose:

```text
editorial_energy_curve
intro_energy_events_added
energy_checkpoints_added
intro_energy_movement
rhythm_summary
```

`editorial_energy_curve` records timestamp, energy, source (`semantic` or `generated`), block and event id.
Use real rendered Reels later to calibrate the curve; do not pretend this value is measured audience retention.

## QC / guard

Current profile:

```text
nominal zoom levels = 1.03 / 1.05 / 1.08 / 1.12
profile max         = 1.12
normal min gap      ~= 3.0 s
cadence fallback    ~= 4.5-6.0 s
slow_push           ~= 2.0 s
slow_push settle    >= 0.5 s
Family-B pause      <=450 ms preserved; longer -> ~450 ms
```

`pipeline_guard.py` continues to accept `1.7.6*` semantic/zoom artifacts and rejects mixed old provenance.
