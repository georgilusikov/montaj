# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

**Goal:** keep the useful architectural fix from v1.7.1 without turning the skill into a framework.

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

1. **WHY** — is this moment semantically important enough to change framing, and is the energy building, peaking, releasing, or staying neutral?
2. **CAN** — which of CONTEXT / ARGUMENT / EMPHASIS are physically safe here?
3. **WHEN** — which nearby boundary is safe for the transition?
4. **HOW** — hold, step/reframe, or slow_push?

Gaze/head pose may improve WHEN, but must not create WHY.

## Inputs

`analysis.json` may contain only observations/evidence:

- transcript semantic events (`importance`, optional `type`, optional `direction`)
- face ratio / face center / hair top
- optional normalized `face_bbox: [left, top, right, bottom]`
- caption overlap / hard gesture or prop block
- blink / blur flags
- long-eye-closure / pose-unsafe / strong-head-turn flags when available
- pause / word-boundary / head-return candidates
- source dimensions and optional quality hints

## Shot states

Use semantic states, not fixed plan numbers:

- `CONTEXT`
- `ARGUMENT`
- `EMPHASIS`

Default desired face-ratio targets are provisional:

- CONTEXT: 0.30
- ARGUMENT: 0.35
- EMPHASIS: 0.41

The targets describe the desired composition. They do **not** authorize arbitrary zoom strength.

### Artistic zoom caps

Default state caps:

- CONTEXT: **1.05x**
- ARGUMENT: **1.12x**
- EMPHASIS: **1.20x**

Global absolute cap: **1.20x**.

The intensity cap also applies:

- calm: 1.10x
- moderate: 1.16x
- dynamic: 1.20x

Therefore, for the normal `moderate` talking-head profile, even EMPHASIS is capped at **1.16x**.

### 4K rule

`quality_cap` is a **technical image-quality limit only**. It never raises the artistic cap.

Example:

```text
4K source quality_cap = 1.60
moderate EMPHASIS
=> effective cap = min(1.60 quality, 1.16 style, 1.20 state, 1.20 absolute)
=> 1.16x maximum
```

A plan that uses 1.33x ARGUMENT or 1.60x EMPHASIS is **not v1.7 Lite compliant**, even when the source is 4K. `simple_qc.py` must reject it.

The planner computes scale from the actual face ratio and clamps it by:

- state cap
- style/intensity cap
- absolute zoom cap
- quality cap
- geometry safety

If three distinct states do not fit, use two. If two do not fit, use one. Never invent a fake third plan. `scale < 1.00` is forbidden.

## Geometry safety

For each candidate event, inspect a short time window around it. A state is safe only if all sampled frames keep:

- crop inside source bounds
- hair/head inside frame
- face below hard maximum size
- face box inside the fixed crop with a small edge margin across the whole window
- no caption overlap
- no hard gesture/prop block

The selected crop is one fixed crop for the event window; do not assume the renderer can re-center differently on every frame.

If `face_bbox` is unavailable, the Lite planner derives a conservative approximate face box from `face_cx`, `face_cy`, and `face_ratio`. This is intentionally simple: it exists to stop a close crop when the subject travels too far inside the event window.

## WHY

Each semantic event contains `importance` in `[0,1]` and may also contain semantic `type` and `direction`.

### Importance = how much emphasis the sentence deserves

Simple default mapping:

- `<0.40` -> CONTEXT
- `0.40..0.74` -> ARGUMENT
- `>=0.75` -> EMPHASIS

### Direction = where the visual energy should move

Optional values:

- `build` — build tension, but never jump directly to EMPHASIS; at most move toward ARGUMENT.
- `peak` — use the normal importance/type target; a strong event may reach EMPHASIS.
- `release` — return toward CONTEXT even if the sentence itself is important.
- `neutral` — explicitly preserve the current framing unless geometry forces degradation.

If `direction` is absent or unknown, the planner keeps the previous v1.7 Lite behavior and uses importance/type directly.

This gives dramaturgy without a pattern engine. Example:

```text
build   -> ARGUMENT
peak    -> EMPHASIS
release -> CONTEXT
```

But this is **not** a mandatory repeating sequence. Events can be `peak -> release -> build`, several neutral events can hold the same state, and missing intermediate states simply collapse according to geometry. Patterns such as Ladder/Wave remain descriptions of the resulting timeline, not planning rules.

## WHEN

Choose the best nearby safe candidate boundary.

Hard reject:

- blink
- blur
- hard gesture/prop conflict
- long eye closure
- unsafe strong pose/head turn

Soft bonuses:

- word boundary
- pause
- head return
- proximity to semantic event

### Minimum dwell

To avoid nervous zoom flicker, a real framing change must normally respect a minimum dwell since the previous change:

- calm: **2000 ms**
- moderate: **1500 ms**
- dynamic: **1200 ms**

A very strong explicit `peak` (`importance >= 0.90`) may use a shorter provisional minimum of **800 ms**. Holds do not reset the dwell timer.

If no safe boundary survives safety + dwell, keep the current framing.

## Motion

Only three outputs:

- `hold`
- `step`
- `slow_push`

Use `slow_push` for strong semantic emphasis when the scale difference is too small for a clean perceptual step. Otherwise use `step` for a meaningful discrete change.

No pattern engine in v1.7 Lite. Ladder/Wave/Punch may be used later as descriptions of resulting timelines, not as planning constraints.

## Renderer contract

`zoom_plan.json` is the source of truth and contains final pixel crops:

```json
{
  "start_ms": 1200,
  "end_ms": 3100,
  "state": "EMPHASIS",
  "direction": "peak",
  "motion": "slow_push",
  "crop_start": [0, 0, 1080, 1920],
  "crop_end": [54, 80, 964, 1714],
  "why": "semantic_peak"
}
```

Renderer must execute these crops; it must not re-solve composition.

Content-removing jumpcuts remain separate from framing decisions.

## Pause removal remains a separate content-edit layer

The zoom planner does **not** decide which speech pauses to delete. The existing talking-head skill keeps that responsibility before framing:

- dense speech / short pauses -> preserve continuity;
- removable silence -> trim according to the speech-cleanup policy and preserve words;
- remaining pauses may still receive a positive WHEN bonus for a framing transition.

This separation is intentional: removing footage and changing crop are different editing decisions.

## QC Lite

After render/plan check only:

1. all crops stay inside source bounds;
2. no forbidden scale below 1.00;
3. no crop/declared scale exceeds the state/artistic cap;
4. face/hair/captions remain safe in planned frames;
5. planned zoom actually changes crop when motion != hold;
6. ASR/text integrity can be checked by the existing skill flow.

No critic registry, provenance framework, pattern lifecycle, director provider, retention gate, or complex report schema in v1.7 Lite.

## Definition of done

- `zoom_planner.py` produces a valid plan from observations + semantic events;
- 1–3 feasible states work automatically;
- WHY is independent from gaze;
- importance controls emphasis level while direction can express build / peak / release / neutral;
- direction does not introduce a hard repeating zoom pattern;
- 4K quality cannot silently create an aggressive zoom;
- face travel can degrade an unsafe close framing instead of clipping the subject;
- blink/blur/long-eye-closure/strong-pose safety is preserved;
- minimum dwell prevents nervous repeated reframes;
- pause trimming remains a separate content-edit decision;
- renderer accepts canonical crop coordinates;
- simple QC catches invalid crops, no-op zooms, and excessive zoom strength;
- implementation stays small enough to understand and modify directly.
