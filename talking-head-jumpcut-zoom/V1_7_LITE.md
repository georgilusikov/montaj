# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

**Goal:** dynamic talking-head editing without turning the skill into a framework.

## Pipeline

```text
normalized source
        ↓
Whisper word timings
        ↓
scripts/speech_cleanup.py
        ↓
cleanup_plan.json + dense.mp4 + remapped output_words
        ↓
perception + semantic analysis on dense timeline
        ↓
analysis.json + content_cuts_ms
        ↓
scripts/zoom_planner.py
        ↓
zoom_plan.json
        ↓
scripts/render_zoom.py
        ↓
final.mp4
        ↓
scripts/simple_qc.py
```

There are two independent edit planes:

1. **CONTENT / PACING** — remove long pauses and create jumpcuts.
2. **FRAMING / SEMANTICS** — use zoom/reframe only when meaning justifies it.

Zoom must never be used as a substitute for speech cleanup.

---

## Phase 1 — strict speech cleanup

The old skill already treated pause removal as a separate first phase. Lite restores that contract with one small deterministic script: `scripts/speech_cleanup.py`.

Input:

```json
{
  "source": {"duration_ms": 88000},
  "config": {
    "mode": "strict",
    "cut_threshold_ms": 500,
    "target_gap_ms": 180,
    "head_pad_ms": 120,
    "tail_pad_ms": 350,
    "audio_fade_ms": 15
  },
  "words": [
    {"text": "hello", "start_ms": 500, "end_ms": 820}
  ]
}
```

Default policy:

- pauses `<= 500 ms` are preserved;
- pauses `> 500 ms` are reduced to about `180 ms` total silence;
- keep about `120 ms` before the first spoken word;
- keep about `350 ms` after the final spoken word;
- use tiny `15 ms` audio fades around hard cuts to avoid clicks;
- do **not** remove fillers, false starts or words in Lite `strict` mode.

Output:

- `kept_segments`: exact source→output mapping;
- `content_cuts_ms`: jumpcut positions on the dense output timeline;
- `removed_gaps`: audit of removed silence;
- `output_words`: original transcript words remapped to dense output time;
- optional rendered `dense.mp4` when `--input-video` and `--output-video` are supplied.

The dense output timeline is the canonical timeline for all later semantic/framing decisions.

---

## Core principle

There are two different reasons to change the picture:

1. **PACING** — keep the visual stream alive, normally with a content jumpcut / same-scale reframe.
2. **SEMANTICS** — emphasize meaning with framing/zoom.

```text
visual refresh every ~2–5 s
        ≠
zoom every ~2–5 s
```

Subtitles are external and do not count as camera/framing changes here.

---

## Visual vocabulary

Default moderate style:

```text
CONTEXT     1.00x       exact source frame / visual home
ARGUMENT    ~1.10–1.12  normal semantic punch
EMPHASIS    ~1.16       rare strong peak (dynamic may reach 1.20)
```

`CONTEXT` is always the full source frame. 4K quality may make crops cleaner but never raises artistic caps.

The planner computes accent scale from actual face size and geometry. If a close state is unsafe or perceptually redundant, downgrade/collapse it.

---

## WHY: semantics

Importance:

- `< 0.40` → CONTEXT
- `0.40 .. 0.84` → ARGUMENT
- `>= 0.85` → EMPHASIS

Optional direction:

- `build` — rising tension;
- `peak` — strongest justified beat;
- `release` — return to CONTEXT;
- `neutral` — hold.

Gaze/head pose never creates WHY. It may only improve WHEN.

Useful semantic triggers include antithesis, change of subject, warning, important number/rule, quote/axiom, conclusion and punchline. These are LLM hints, not Python keyword rules.

---

## Motion

### Default: step/reframe

Normal ARGUMENT and EMPHASIS use a clean discrete reframe on a safe word/clause boundary.

```text
1.00 → 1.12 → 1.00
```

This remains the primary Reels/Shorts visual language.

### Rare gradual BUILD

A slow push is **not automatic for every `build`**.

The semantic layer must explicitly request:

```json
{"direction":"build", "motion_hint":"slow_push"}
```

Then a first moderate BUILD from CONTEXT uses a partial crop around **1.05x** and reaches it over roughly **1.5–3.0 s** (default ~2.4 s).

```text
1.00 ───slow──→ ~1.05
```

A direct thesis/antithesis should normally skip the soft build and jump straight to ~1.12.

Slow pushes are interpolated densely at 60 Hz with easing. The old 10 Hz stair-step interpolation is forbidden.

---

## Zoom episode duration

ARGUMENT/EMPHASIS are temporary semantic episodes, not persistent states.

- `micro_punch`: **0.8–1.4 s**
- `beat`: **1.5–2.4 s**
- `argument_hold`: **2.5–3.5 s**

If no explicit type is supplied, infer it from semantic-clause duration.

After an episode, normally return to exact CONTEXT 1.00x. Closely connected `build → peak` beats may stay close to avoid a one-frame base flash.

---

## WHEN

Hard reject transition points with:

- blink / long eye closure;
- blur;
- unsafe head pose / strong turn;
- hard gesture/prop conflict;
- unsafe crop geometry.

Soft bonuses:

- semantic proximity;
- word boundary;
- pause;
- head return;
- preferred camera rhythm.

Minimum dwell:

- calm: 2000 ms
- moderate: 1500 ms
- dynamic: 1200 ms
- very strong explicit peak: provisional 800 ms

Auto-return should not intentionally cut through an unsafe gesture; if a safer boundary is available nearby, prefer it. The duration band is guidance, not permission to cut mechanically in the middle of motion.

---

## The 2–5 second visual-rhythm rule

The **content/jumpcut layer owns cadence**. `zoom_planner.py` accepts `content_cuts_ms` from Phase 1 and combines them with real framing changes.

If the known timeline still contains a visual gap larger than the style maximum (moderate: ~5 s), the planner emits a non-semantic `cadence_request` such as:

```json
{
  "at_ms": 10500,
  "preferred_action": "jumpcut_same_scale",
  "fallback_action": "hold_if_no_safe_cut",
  "semantic_trigger": false,
  "why": "visual_refresh_gap"
}
```

`cadence_requests` are requests to the content-cut layer, not camera motions. If there is no safe/natural extra cut, holding is better than manufacturing a fake zoom.

There is **no ambient `1.00 ↔ 1.04/1.05` watchdog**.

---

## Geometry

For each semantic event inspect a short temporal window and keep:

- crop inside source;
- face/hair safely inside crop;
- face below max size;
- caption/gesture/prop safety;
- one fixed crop safe across the event window.

Renderer receives final pixel crops and never re-solves composition.

---

## Renderer contract

Phase 1 renders the dense speech timeline. Phase 2 `render_zoom.py` operates on that dense video only.

`zoom_plan.json` contains:

- semantic `decisions`;
- explicit `returns` to CONTEXT;
- `content_cuts_ms` for cadence awareness;
- non-rendering `cadence_requests` for optional additional content cuts.

Renderer executes semantic framing decisions + returns. It does not manufacture cadence zooms.

---

## QC Lite

Check:

1. speech cleanup output mapping is contiguous;
2. words remain in order and are remapped to output time;
3. crop bounds;
4. no scale below 1.00;
5. CONTEXT is exact source framing;
6. accent state caps;
7. non-hold motion actually changes crop;
8. cadence requests are non-semantic;
9. transcript/text integrity is unchanged by strict cleanup.

---

## Definition of done

- long pauses are removed **before** semantic zoom planning;
- strict cleanup never removes spoken words;
- dense output provides `kept_segments`, `content_cuts_ms` and remapped `output_words`;
- WHY is semantic and independent from gaze;
- CONTEXT = 1.00x source frame;
- ARGUMENT is the common ~1.12 punch;
- EMPHASIS is rare;
- zoom duration follows the phrase;
- auto-return prevents close framing from sticking;
- slow BUILD is explicit and rare;
- no ambient camera breathing;
- visual cadence is maintained primarily by speech/content jumpcuts, with `cadence_requests` only when a >5 s gap remains.
