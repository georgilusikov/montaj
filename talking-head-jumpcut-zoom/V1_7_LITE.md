# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

**Goal:** keep the useful semantic/geometry fix without turning the skill into a framework.

## Pipeline

```text
SKILL.md
  -> analysis.json
  -> scripts/zoom_planner.py
  -> zoom_plan.json
  -> scripts/render_zoom.py
  -> final.mp4
  -> scripts/simple_qc.py
```

## Core rule

Every framing change answers four questions:

1. **WHY** — is this moment semantically important, and is the energy building, peaking, releasing, or neutral?
2. **CAN** — which of CONTEXT / ARGUMENT / EMPHASIS are physically safe here?
3. **WHEN** — which nearby boundary is safe and rhythmically natural?
4. **HOW** — hold, step/reframe, or slow_push?

Gaze/head pose may improve WHEN, but must not create WHY.

## Inputs

`analysis.json` contains observations/evidence only:

- semantic events: `importance`, optional `type`, optional `direction`;
- optional `zoom_duration_type`: `micro_punch`, `beat`, or `argument_hold`;
- face ratio / face center / hair top;
- optional normalized `face_bbox`;
- caption overlap / gesture or prop hard block;
- blink / blur / long eye closure / unsafe pose flags;
- pause / word-boundary / head-return boundary candidates;
- source dimensions and optional quality hints.

## Shot states

Use semantic states, not fixed plan numbers:

- `CONTEXT`
- `ARGUMENT`
- `EMPHASIS`

Default desired face-ratio targets remain provisional:

- CONTEXT: 0.30
- ARGUMENT: 0.35
- EMPHASIS: 0.41

Default artistic caps:

- CONTEXT: **1.00x** — exact source framing, no crop;
- ARGUMENT: **1.12x**;
- EMPHASIS: **1.20x**.

`CONTEXT` is intentionally special: it is the visual home/base, so it does **not** chase the 0.30 face-ratio target by cropping. The target remains diagnostic; the actual default CONTEXT crop is always the full source frame.

Global absolute cap: **1.20x**.

Intensity caps:

- calm: 1.10x
- moderate: 1.16x
- dynamic: 1.20x

For normal `moderate`, even EMPHASIS is therefore capped at **1.16x**.

### 4K rule

`quality_cap` is technical only. It never raises the artistic cap.

```text
4K quality_cap = 1.60
moderate EMPHASIS
=> min(1.60 quality, 1.16 style, 1.20 state, 1.20 absolute)
=> 1.16x maximum
```

The planner computes ARGUMENT/EMPHASIS scale from actual face size. CONTEXT remains exact source framing. If distinct safe accent states do not fit, collapse them; never invent a fake third state. `scale < 1.00` is forbidden.

## Geometry safety

For each semantic event inspect a short temporal window. A candidate state is safe only if sampled frames keep:

- crop inside source bounds;
- hair/head inside frame;
- face below hard maximum size;
- face box inside one fixed crop across the whole event window;
- no caption overlap;
- no hard gesture/prop block.

Renderer receives the final pixel crop. It must not re-solve composition.

## WHY: semantic energy

### Importance

Importance answers **how strong the visual emphasis deserves to be**.

Calibrated default mapping:

- `< 0.40` -> CONTEXT
- `0.40 .. 0.84` -> ARGUMENT
- `>= 0.85` -> EMPHASIS

EMPHASIS is intentionally rare. Normal semantic accents should usually remain ARGUMENT.

Semantic types that often deserve higher importance include:

- contrast / antithesis: `X, but Y`, `not X — Y`;
- change of subject or point of view;
- important number / rule / list conclusion;
- warning;
- punchline;
- quote / axiom / final conclusion.

These are semantic hints for the LLM/analysis layer, **not Python keyword triggers**.

### Direction

Optional values:

- `build` — increase visual tension, at most toward ARGUMENT;
- `peak` — allow the semantic target; a strong event may reach EMPHASIS;
- `release` — return toward CONTEXT and restore visual breathing room;
- `neutral` — preserve current framing unless geometry forces degradation.

```text
build   -> visually closer / more focused
peak    -> strongest justified framing
release -> wider / calmer framing
neutral -> hold
```

This is not a mandatory repeating pattern. The goal is controlled visual tension and relief.

## WHEN: safety first, rhythm second

Hard reject:

- blink;
- blur;
- hard gesture/prop conflict;
- long eye closure;
- unsafe strong pose/head turn.

Soft bonuses:

- semantic proximity;
- word boundary;
- pause;
- head return;
- preferred camera rhythm.

### Minimum dwell

To avoid nervous flicker:

- calm: **2000 ms**
- moderate: **1500 ms**
- dynamic: **1200 ms**

A very strong explicit peak (`importance >= 0.92`) may use the provisional **800 ms** minimum.

### Preferred camera cadence

The camera-layer reference suggests a normal framing refresh roughly every **2.4–2.7 s**, but this is only a soft preference:

- calm target: ~3.0 s
- moderate target: ~2.5 s
- dynamic target: ~2.2 s

Meaning wins over the timer. The planner must never manufacture a zoom just because the cadence target expired.

### Captions are separate

Caption/subtitle pacing is handled elsewhere and must not drive the zoom planner.

```text
camera/framing rhythm != caption rhythm
```

## Zoom episodes: duration + return

ARGUMENT and EMPHASIS are normally **temporary semantic episodes**, not persistent states that remain until the next semantic event.

Default duration bands, calibrated from the reference montage analysis:

- `micro_punch`: **0.8–1.4 s** — one word / short prohibition / tiny antithesis;
- `beat`: **1.5–2.4 s** — one compact semantic clause;
- `argument_hold`: **2.5–3.5 s** — a longer explanatory argument.

If `zoom_duration_type` is absent, the planner infers the band from the semantic clause length (`end_ms - start_ms`) and clamps it to the band.

After the zoom episode ends, the planner normally emits an automatic return to **exact source framing (CONTEXT 1.00x)**:

```text
CONTEXT 1.00x
  -> ARGUMENT / EMPHASIS
  -> hold for semantic clause
  -> CONTEXT 1.00x
```

This prevents the close framing from sticking for 5–10 seconds simply because the next semantic event has not arrived yet.

### Sustained tension

Do **not** force a visible return between tightly connected semantic beats.

If a nearby following event is explicitly `build` or `peak` and arrives within the current episode (or within a small grace window), the first episode may stay close and the next event extends/re-shapes the tension:

```text
ARGUMENT -> EMPHASIS -> CONTEXT
```

instead of:

```text
ARGUMENT -> CONTEXT -> EMPHASIS
```

with an ugly split-second flash of the base framing.

The semantic layer may also set `zoom_duration_type` explicitly when it knows that a phrase is a micro-punch, normal beat, or extended argument.

## Motion

Only three outputs:

- `hold`
- `step`
- `slow_push`

**Default visual language remains `step/reframe`.** The reference montage analysis supports hard/reframe cuts as the normal accent language, so v1.7 Lite must not convert all semantic zooms into smooth pushes.

`slow_push` stays a rare option for a strong semantic emphasis when the crop delta is too small for a clean discrete step. It is not the default transition style.

No pattern engine. Ladder/Wave/Punch may later describe the resulting timeline, but do not generate it.

## Content cuts stay separate

Removing speech pauses and changing framing are separate decisions.

The zoom planner does not decide which spoken pauses to remove. Existing speech-cleanup logic remains responsible for word integrity and pause trimming. Remaining safe pauses can still receive a WHEN bonus.

## Renderer contract

`zoom_plan.json` contains semantic decisions plus explicit automatic returns. Example decision:

```json
{
  "start_ms": 1200,
  "end_ms": 3200,
  "state": "ARGUMENT",
  "direction": "build",
  "motion": "step",
  "zoom_duration_type": "beat",
  "zoom_duration_ms": 2000,
  "auto_return": true,
  "crop_start": [0, 0, 1080, 1920],
  "crop_end": [48, 74, 982, 1746]
}
```

The top-level `returns` array contains the exact CONTEXT return commands. Renderer executes both semantic decisions and returns; it must not invent timing or composition.

## QC Lite

Check only:

1. crops inside source bounds;
2. no scale below 1.00;
3. CONTEXT must remain at 1.00x by default;
4. no accent crop above artistic/state cap;
5. face/hair/captions remain safe;
6. non-hold motion actually changes crop;
7. ASR/text integrity through the existing skill flow.

No critic registry, provenance framework, pattern lifecycle, director provider, retention gate, or complex report schema.

## Definition of done

- WHY is independent from gaze;
- importance controls emphasis level;
- direction creates build / peak / release / neutral visual energy;
- CONTEXT is exact source framing (1.00x);
- EMPHASIS stays rare by default;
- camera cadence is a soft prior, not a zoom generator;
- zoom duration follows the semantic clause rather than a fixed metronome;
- a finished zoom episode normally returns to CONTEXT;
- adjacent build/peak beats can sustain tension without a base-frame flash;
- geometry automatically collapses infeasible accent states;
- 4K cannot silently create aggressive framing;
- blink/blur/pose/gesture safety is preserved;
- renderer receives canonical crop coordinates and explicit return timing;
- step/reframe remains the default; slow_push remains rare;
- simple QC catches invalid/no-op/excessive zoom;
- implementation remains small enough to understand directly.
