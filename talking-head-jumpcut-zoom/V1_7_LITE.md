# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

**Goal:** dynamic talking-head editing without turning the skill into a framework.

## Pipeline

```text
speech cleanup / jumpcuts
        ↓ content_cuts_ms
analysis.json
        ↓
zoom_planner.py
        ↓
zoom_plan.json
        ↓
render_zoom.py
        ↓
final.mp4
        ↓
simple_qc.py
```

## Core principle

There are two different reasons to change the picture:

1. **PACING** — keep the visual stream alive, normally with a content jumpcut / same-scale reframe.
2. **SEMANTICS** — emphasize meaning with framing/zoom.

Do not use zoom to solve every pacing gap.

```text
visual refresh every ~2–5 s
        ≠
zoom every ~2–5 s
```

## Visual vocabulary

Default moderate style:

```text
CONTEXT     1.00x       exact source frame / visual home
ARGUMENT    ~1.10–1.12  normal semantic punch
EMPHASIS    ~1.16       rare strong peak (dynamic may reach 1.20)
```

`CONTEXT` is always the full source frame. 4K quality may make crops cleaner but never raises artistic caps.

The planner computes accent scale from actual face size and geometry. If a close state is unsafe or perceptually redundant, downgrade/collapse it.

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

It may then continue to a real ARGUMENT/EMPHASIS punch if the meaning escalates.

A direct thesis/antithesis should normally skip the soft build and jump straight to ~1.12.

### Smooth rendering

Slow pushes are interpolated densely at 60 Hz with easing. The old 10 Hz stair-step interpolation is forbidden.

## Zoom episode duration

ARGUMENT/EMPHASIS are temporary semantic episodes, not persistent states.

- `micro_punch`: **0.8–1.4 s**
- `beat`: **1.5–2.4 s**
- `argument_hold`: **2.5–3.5 s**

If no explicit type is supplied, infer it from semantic-clause duration.

After an episode, normally return to exact CONTEXT 1.00x. Closely connected `build → peak` beats may stay close to avoid a one-frame base flash.

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

## The 2–5 second visual-rhythm rule

Subtitles are external and do not count here.

The **jumpcut/content layer owns visual cadence**. `zoom_planner.py` accepts optional `content_cuts_ms` and combines them with real framing changes.

If the known timeline would contain a visual gap larger than the style maximum (moderate: ~5 s), the planner emits a non-semantic request:

```json
{
  "at_ms": 10500,
  "preferred_action": "jumpcut_same_scale",
  "fallback_action": "hold_if_no_safe_cut",
  "semantic_trigger": false,
  "why": "visual_refresh_gap"
}
```

These top-level `cadence_requests` are requests to the content-cut layer — **not camera motions**.

For moderate:

- preferred refresh target: ~3.5 s;
- intended range: roughly 2–5 s;
- if there is no safe/natural cut, holding the shot is better than manufacturing a fake zoom.

### Explicitly removed

There is **no ambient `1.00 ↔ 1.04/1.05` watchdog**. It produced continuous camera breathing and too many movements.

## Geometry

For each semantic event inspect a short temporal window and keep:

- crop inside source;
- face/hair safely inside crop;
- face below max size;
- caption/gesture/prop safety;
- one fixed crop safe across the event window.

Renderer receives final pixel crops and never re-solves composition.

## Renderer contract

`zoom_plan.json` contains:

- semantic `decisions`;
- explicit `returns` to CONTEXT;
- `content_cuts_ms` (when supplied);
- non-rendering `cadence_requests` for the jumpcut layer.

Renderer executes only semantic framing decisions + returns. It does not render cadence requests.

## QC Lite

Check only:

1. crop bounds;
2. no scale below 1.00;
3. CONTEXT is exact source framing;
4. accent state caps;
5. non-hold motion actually changes crop;
6. cadence requests are non-semantic and surfaced as warnings;
7. ASR/text integrity through the existing content-cut flow.

## Definition of done

- WHY is semantic and independent from gaze;
- CONTEXT = 1.00x source frame;
- ARGUMENT is the common ~1.12 punch;
- EMPHASIS is rare;
- zoom duration follows the phrase;
- auto-return prevents close framing from sticking;
- slow BUILD is explicit and rare, not automatic;
- slow motion is smooth (60 Hz + easing);
- no ambient camera breathing;
- visual cadence is maintained primarily by jumpcuts, with planner `cadence_requests` when a >5 s gap is predicted;
- implementation stays small and directly understandable.
