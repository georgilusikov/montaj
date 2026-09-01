# Talking-Head Jumpcut & Zoom Editor v1.7.1 Lite

**Goal:** dynamic talking-head editing with deterministic timing and fail-closed verification, without turning the skill into a large framework.

## Core invariant

There are two independent edit planes:

1. **CONTENT / PACING** — remove long pauses and create jumpcuts.
2. **FRAMING / SEMANTICS** — change crop/zoom only when meaning justifies it.

```text
visual refresh every ~2–5 s
        ≠
zoom every ~2–5 s
```

The v1.7.1 patch fixes a critical v1.7 Lite gap: the old pipeline expected `semantic_events` but did not define a mandatory producer for them. That allowed an agent to invent an ad-hoc `build_analysis.py`, omit semantics, render an unchanged 100% crop, and still receive QC PASS.

---

## Canonical pipeline

```text
normalized source
        ↓
Whisper word timings
        ↓
speech_cleanup.py
        ↓
cleanup_plan.json + dense.mp4 + output_words + content_cuts_ms
        ↓
AGENT SEMANTIC PASS (WHY only)
        ↓
semantic_marks.json
        ↓
semantic_events.py
        ↓
semantic_events.json
        ↓
perception / frame_defects.py
        ↓
analysis.json
        ↓
zoom_planner.py
        ↓
zoom_plan.json
        ↓
simple_qc.py  [PRE-RENDER, FAIL-CLOSED]
        ↓ PASS only
render_zoom.py
        ↓
final.mp4
        ↓
post_render_qc.py  [ACTUAL PIXELS]
        ↓
accepted final
```

### Non-negotiable execution rules

- Never call `zoom_planner.py` before semantic marks exist.
- Never replace canonical scripts with ad-hoc agent-written equivalents during a production run.
- Never infer semantic WHY from gaze, head-return, elapsed time, or jumpcut cadence.
- Never accept a long talking-head edit with zero visible semantic framing changes unless an explicit editorial no-zoom override is set.
- JSON validity is not proof that the rendered artifact contains the planned crop changes.

---

## Phase 1 — strict speech cleanup

`speech_cleanup.py` owns pacing.

Family B default policy:

- pauses `<= 250 ms` preserved;
- pauses `> 250 ms` reduced to about `180 ms`;
- about `120 ms` head pad;
- about `350 ms` tail pad;
- `15 ms` audio fades around hard cuts;
- strict mode does not remove fillers, false starts or words.

Output:

- `kept_segments`;
- `content_cuts_ms`;
- `removed_gaps`;
- `output_words` remapped to dense output time;
- optional `dense.mp4`.

The dense output timeline is canonical for every later timestamp.

---

## Phase 2A — Semantic Director contract

The agent/LLM owns **WHY**, not milliseconds.

Input to `semantic_events.py`:

```json
{
  "words": [
    {"text": "Nunca", "start_ms": 0, "end_ms": 280},
    {"text": "se", "start_ms": 300, "end_ms": 390}
  ],
  "semantic_marks": [
    {
      "id": "hook",
      "start_word": 0,
      "end_word": 6,
      "importance": 0.78,
      "direction": "build",
      "motion_hint": "step",
      "zoom_duration_type": "beat",
      "why": "contrarian opening thesis"
    }
  ]
}
```

Required per mark:

- `start_word`;
- `end_word`;
- `importance` in `0..1`;
- non-empty `why`.

Optional:

- `direction`: `build|peak|release|neutral|ratchet_1|ratchet_2|ratchet_3`;
- `motion_hint`: `auto|step|slow_push`;
- `zoom_duration_type`: `micro_punch|beat|argument_hold`;
- `transition_ms`.

`semantic_events.py` then owns timing:

- maps word indices to exact dense `t_ms/end_ms`;
- generates nearby word-boundary candidates;
- marks pauses as boundary bonuses;
- validates word order, ranges and semantic schema.

### Fail-closed semantic rule

If spoken span is at least 8 seconds and `semantic_marks=[]`, the semantic producer raises an error by default.

Explicit exception:

```json
{
  "config": {
    "allow_no_semantic_events": true
  }
}
```

This exception must mean an intentional editorial no-zoom decision, not a failed semantic pass.

---

## WHY model

Importance:

- `< 0.40` → CONTEXT;
- `0.40 .. 0.84` → ARGUMENT;
- `>= 0.85` → EMPHASIS.

Useful semantic triggers:

- hook / contrarian thesis;
- antithesis;
- important rule/number;
- warning / consequence;
- argument change;
- example → conclusion;
- punchline / conclusion;
- list escalation.

Direction:

- `build` — rising tension;
- `peak` — strongest justified beat;
- `release` — return to CONTEXT;
- `neutral` — hold;
- `ratchet_1/2/3` — explicit escalation in lists.

Gaze/head pose never creates WHY. It only improves WHEN.

---

## Visual vocabulary

Default gold-lite:

```text
CONTEXT     1.00x
ARGUMENT    ~1.06–1.10
EMPHASIS    ~1.12
ratchet_3   ~1.16
```

Dynamic may reach 1.16; hard cap 1.20.

Actual scale is constrained by:

- real face size;
- geometry;
- quality cap;
- style cap;
- state cap;
- crop safety.

4K does not silently create more aggressive artistic zooms.

---

## Motion

### Default step/reframe

Normal ARGUMENT and EMPHASIS:

```text
1.00 → 1.12 → 1.00
```

### Rare slow push

Only when semantic mark explicitly requests:

```json
{"direction":"build","motion_hint":"slow_push"}
```

Soft build targets around:

- calm `1.03`;
- moderate `1.05`;
- dynamic `1.06`.

Transition is eased densely at 60 Hz.

### Episode duration

- `micro_punch`: 0.5–1.2 s;
- `beat`: 1.2–2.0 s;
- `argument_hold`: 2.0–2.5 s.

ARGUMENT/EMPHASIS are temporary episodes. After the beat, normally return to exact CONTEXT.

---

## WHEN / feasibility

Hard reject transition points with:

- blink / long eye closure;
- MAR mouth distortion;
- blur;
- unsafe pose / strong head turn;
- hard gesture/prop conflict;
- unsafe crop / face travel / headroom.

Soft bonuses:

- semantic proximity;
- word boundary;
- pause;
- head return;
- preferred cadence.

Minimum dwell:

- calm 2000 ms;
- moderate 1500 ms;
- dynamic 1200 ms;
- very strong peak may provisionally use 800 ms.

### Tripod Lock

No per-frame face-following during hold. Crop center is fixed across the episode. Camera changes only on step or deterministic slow push.

### Eye anchor

For slow push:

```text
Delta_Y = (Y_eyes - Y_center) * (1 - 1/scale)
```

---

## Visual cadence

The pacing layer owns cadence. `content_cuts_ms` are included in the planner so it knows which visual refreshes already exist.

If a known gap remains too long, the planner may emit:

```json
{
  "preferred_action": "jumpcut_same_scale",
  "fallback_action": "hold_if_no_safe_cut",
  "semantic_trigger": false,
  "why": "visual_refresh_gap"
}
```

A cadence request is never converted into a fake semantic zoom.

---

## Pre-render QC — fail closed

`simple_qc.py` checks geometry/caps/no-op constraints plus semantic completeness.

New v1.7.1 gates:

### 1. Missing semantics

For long edits:

```text
duration >= 8 s
AND decisions == []
→ FAIL missing_semantic_events
```

### 2. Semantic pass with no visible output

```text
duration >= 8 s
AND visible_change_count == 0
→ FAIL no_visible_framing_changes
```

### 3. Accent intent collapsed to no-op

```text
ARGUMENT/EMPHASIS intent exists
AND visible_change_count == 0
→ FAIL semantic_accent_became_noop
```

Intentional no-zoom requires:

```json
{"config":{"allow_no_visible_framing":true}}
```

No silent fallback.

---

## Post-render QC — verify actual pixels

`post_render_qc.py` closes the second gap: plan PASS does not prove render execution.

For every visible semantic framing decision:

1. choose a probe frame after the transition landed;
2. read the same frame from `dense.mp4`;
3. apply the planned `crop_end` to create the expected image;
4. read the corresponding frame from `final.mp4`;
5. compare low-resolution grayscale frames using mean absolute error.

If the final frame does not match the planned crop:

```text
FAIL render_does_not_match_planned_crop
```

This catches the regression:

```text
zoom_plan.json says 1.12x
BUT final.mp4 remains 1.00x
```

---

## Golden no-op regression

A 115-second talking-head with meaningful semantics must not pass with:

```json
{
  "decisions": []
}
```

and must not pass with:

```json
{
  "decisions": [
    {
      "status": "KEEP",
      "desired_state": "ARGUMENT",
      "state": "CONTEXT"
    }
  ]
}
```

Tests live in:

```text
tests/test_semantic_contract.py
```

They cover:

- long spoken clip without semantic marks;
- deterministic word-index → ms mapping;
- required semantic reason;
- empty decisions on long video;
- ARGUMENT intent collapsing to no-op;
- explicit intentional no-zoom override.

---

## Canonical commands

```bash
python scripts/speech_cleanup.py speech_input.json cleanup_plan.json \
  --input-video normalized.mp4 \
  --output-video dense.mp4 \
  --export-srt captions.srt

python scripts/semantic_events.py semantic_input.json semantic_events.json

# Assemble:
# analysis.json = source
#               + observations
#               + semantic_events.json#semantic_events
#               + cleanup_plan.json#content_cuts_ms

python scripts/zoom_planner.py analysis.json zoom_plan.json

python scripts/simple_qc.py zoom_plan.json

# only after PRE-RENDER PASS
python scripts/render_zoom.py dense.mp4 zoom_plan.json final.mp4

python scripts/post_render_qc.py dense.mp4 final.mp4 zoom_plan.json
```

Acceptance condition:

```text
semantic contract valid
AND pre-render QC PASS
AND final artifact rendered
AND post-render pixel QC PASS
```
