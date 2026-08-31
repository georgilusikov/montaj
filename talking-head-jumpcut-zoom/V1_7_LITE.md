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

- CONTEXT: **1.05x**
- ARGUMENT: **1.12x**
- EMPHASIS: **1.20x**

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

The planner computes scale from actual face size. If three distinct safe states do not fit, use two; if two do not fit, use one. Never invent a fake third state. `scale < 1.00` is forbidden.

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

This is the minimal dramaturgy model:

```text
build   -> visually closer / more focused
peak    -> strongest justified framing
release -> wider / calmer framing
neutral -> hold
```

It is **not** a mandatory repeating sequence. The semantics may produce `peak -> release -> neutral`, several builds, or a long neutral section.

The goal is controlled visual tension and relief, not a mechanical zoom pattern.

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

The clean camera-layer analysis suggests a normal talking-head camera/framing change roughly every **2.4–2.7 s**.

v1.7 Lite therefore uses only a **soft timing bonus**, not a hard cadence:

- calm target: ~3.0 s
- moderate target: ~2.5 s
- dynamic target: ~2.2 s

Meaning always wins over the timer. If the best semantic boundary occurs at 1.9 s or 3.2 s, the planner may use it.

### Captions are a separate rhythm layer

Kinetic subtitle/text changes may happen faster (roughly ~1.5–1.8 s in the reference analysis), but this cadence must **not** drive the camera zoom planner.

```text
camera/framing rhythm != caption rhythm
```

## Motion

Only three outputs:

- `hold`
- `step`
- `slow_push`

Normal style is predominantly `hold/step`. `slow_push` is reserved for strong semantic emphasis where the crop delta is too small for a clean discrete step.

No pattern engine. Ladder/Wave/Punch may later describe the resulting timeline, but do not generate it.

## Content cuts stay separate

Removing speech pauses and changing framing are separate decisions.

The zoom planner does not decide which spoken pauses to remove. Existing speech-cleanup logic remains responsible for word integrity and pause trimming. Remaining safe pauses can still receive a WHEN bonus.

## Renderer contract

`zoom_plan.json` contains final crops:

```json
{
  "start_ms": 1200,
  "end_ms": 3100,
  "state": "EMPHASIS",
  "direction": "peak",
  "motion": "step",
  "crop_start": [0, 0, 1080, 1920],
  "crop_end": [54, 80, 964, 1714],
  "why": "semantic_peak"
}
```

## QC Lite

Check only:

1. crops inside source bounds;
2. no scale below 1.00;
3. no crop above artistic/state cap;
4. face/hair/captions remain safe;
5. non-hold motion actually changes crop;
6. ASR/text integrity through the existing skill flow.

No critic registry, provenance framework, pattern lifecycle, director provider, retention gate, or complex report schema.

## Definition of done

- WHY is independent from gaze;
- importance controls emphasis level;
- direction creates build / peak / release / neutral visual energy;
- EMPHASIS stays rare by default;
- camera cadence is only a soft prior around ~2.5 s for moderate style;
- caption cadence remains separate;
- geometry automatically collapses to 1–3 feasible states;
- 4K cannot silently create aggressive framing;
- blink/blur/pose/gesture safety is preserved;
- renderer receives canonical crop coordinates;
- simple QC catches invalid/no-op/excessive zoom;
- implementation remains small enough to understand directly.
