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
- source dimensions, optional `duration_ms`, and optional quality hints.

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

- `build` — increase visual tension gradually;
- `peak` — allow the semantic target; a strong event may reach EMPHASIS;
- `release` — return toward CONTEXT and restore visual breathing room;
- `neutral` — preserve current framing unless geometry forces degradation.

For normal `moderate`, a first BUILD from CONTEXT uses a **soft partial ARGUMENT** around **1.05x** and normally reaches it with a slow push over up to **2.4 s**. It remains semantically ARGUMENT, but does not immediately consume the full 1.12x punch.

```text
CONTEXT 1.00
  -> BUILD ~1.05 slowly
  -> ARGUMENT ~1.12 when the thesis needs a punch
  -> EMPHASIS ~1.16–1.20 only for a rare peak
  -> RELEASE 1.00
```

This is not a mandatory ladder. A direct antithesis/punch may still jump straight from 1.00 to ARGUMENT, and a neutral section may remain at 1.00.

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

Meaning wins over the timer. The planner must never manufacture ARGUMENT/EMPHASIS just because the cadence target expired.

### Captions are separate

Caption/subtitle pacing is handled elsewhere and must not drive the zoom planner.

```text
camera/framing rhythm != caption rhythm
```

## Zoom episodes: duration + return

ARGUMENT and EMPHASIS are normally **temporary semantic episodes**, not persistent states that remain until the next semantic event.

Default duration bands:

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

## Visual rhythm watchdog

Subtitles are external, so the camera layer must also avoid excessive visual stasis.

The watchdog is deliberately **not another semantic planner**. If the frame is back at exact CONTEXT and no semantic framing change is coming for too long, it may add a tiny closed ambient cycle:

```text
1.00
  -> slow ambient push ~1.04
  -> slow ambient pull 1.00
```

Defaults:

- moderate maximum intended static gap: about **5.0 s**;
- ambient scale: normally **1.04x**, hard-bounded by the ambient cap **1.05x**;
- each push/pull leg: around **2.2 s** when the gap has room;
- geometry/safety still wins; if even the tiny crop is unsafe, the watchdog skips it rather than clipping the subject.

The watchdog emits top-level `refreshes` with `semantic_trigger=false`. These do not count as ARGUMENT/EMPHASIS and do not alter WHY.

This gives three different sources of visual change:

1. **soft BUILD** — semantic, slow ~1.00 -> 1.05;
2. **ARGUMENT/EMPHASIS step** — semantic, fast punch;
3. **ambient refresh** — non-semantic, slow ~1.00 <-> 1.04 only when neutral footage would otherwise stay static too long.

## Motion

Outputs remain small:

- `hold`
- `step`
- `slow_push`

`step/reframe` remains the normal language for direct semantic punches. A `build` is allowed to use a 2–3 s slow push because gradual motion itself expresses rising tension. `slow_push` is also used by the non-semantic ambient watchdog, but only at a much smaller scale.

No pattern engine. Ladder/Wave/Punch may later describe the resulting timeline, but do not generate it.

## Content cuts stay separate

Removing speech pauses and changing framing are separate decisions.

The zoom planner does not decide which spoken pauses to remove. Existing speech-cleanup logic remains responsible for word integrity and pause trimming. Remaining safe pauses can still receive a WHEN bonus.

## Renderer contract

`zoom_plan.json` contains:

- semantic `decisions`;
- explicit automatic `returns`;
- optional non-semantic `refreshes`.

Renderer executes all three in one ordered command stream and never invents composition. At the same timestamp, an auto-return is applied first and a new semantic command last, so a stale return cannot erase a new punch.

## QC Lite

Check only:

1. crops inside source bounds;
2. no scale below 1.00;
3. CONTEXT must remain at 1.00x by default;
4. no accent crop above artistic/state cap;
5. AMBIENT must remain <= 1.05x and `semantic_trigger=false`;
6. face/hair/captions remain safe;
7. non-hold motion actually changes crop;
8. ASR/text integrity through the existing skill flow.

No critic registry, provenance framework, pattern lifecycle, director provider, retention gate, or complex report schema.

## Definition of done

- WHY is independent from gaze;
- importance controls emphasis level;
- CONTEXT is exact source framing (1.00x);
- BUILD can use a gradual ~1.05x intermediate cue;
- ARGUMENT remains the normal ~1.12x punch;
- EMPHASIS stays rare by default;
- camera cadence is a soft prior, not an emphasis generator;
- neutral footage has a bounded static-watchdog fallback;
- caption cadence remains separate;
- zoom duration follows the semantic clause rather than a fixed metronome;
- a finished zoom episode normally returns to CONTEXT;
- adjacent build/peak beats can sustain tension without a base-frame flash;
- geometry automatically collapses infeasible accent states;
- 4K cannot silently create aggressive framing;
- blink/blur/pose/gesture safety is preserved;
- renderer receives canonical crop coordinates and explicit timing;
- simple QC catches invalid/no-op/excessive/semantic-ambient mistakes;
- implementation remains small enough to understand directly.
