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

1. **WHY** — is this moment semantically important enough to change framing?
2. **CAN** — which of CONTEXT / ARGUMENT / EMPHASIS are physically safe here?
3. **WHEN** — which nearby boundary is safe for the transition?
4. **HOW** — hold, step/reframe, or slow_push?

Gaze/head pose may improve WHEN, but must not create WHY.

## Inputs

`analysis.json` may contain only observations/evidence:

- transcript semantic events (`importance`, optional `type`)
- face ratio / face center / hair top
- caption overlap / hard gesture or prop block
- blink / blur flags
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

The planner computes scale from the actual face ratio and clamps it by:

- style cap: calm 1.10 / moderate 1.16 / dynamic 1.20
- quality cap: user/config value, default 1.16
- geometry safety

If three distinct states do not fit, use two. If two do not fit, use one. Never invent a fake third plan. `scale < 1.00` is forbidden.

## Geometry safety

For each candidate event, inspect a short time window around it. A state is safe only if all sampled frames keep:

- crop inside source bounds
- hair/head inside frame
- face below hard maximum size
- no caption overlap
- no hard gesture/prop block

The selected crop is one fixed crop for the event window; do not assume the renderer can re-center differently on every frame.

## WHY

Input semantic event contains `importance` in `[0,1]` and optional semantic `type`.

Simple default mapping:

- `<0.40` -> CONTEXT
- `0.40..0.74` -> ARGUMENT
- `>=0.75` -> EMPHASIS

This mapping is deliberately simple and easy to calibrate later.

## WHEN

Choose the best nearby safe candidate boundary.

Hard reject:

- blink
- blur
- hard gesture/prop conflict

Soft bonuses:

- word boundary
- pause
- head return
- proximity to semantic event

If no safe boundary exists, keep the current framing.

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
  "motion": "slow_push",
  "crop_start": [0, 0, 1080, 1920],
  "crop_end": [54, 80, 964, 1714],
  "why": "semantic_importance"
}
```

Renderer must execute these crops; it must not re-solve composition.

Content-removing jumpcuts remain separate from framing decisions.

## QC Lite

After render check only:

1. all crops stay inside source bounds;
2. no forbidden scale below 1.00;
3. face/hair/captions remain safe in planned frames;
4. planned zoom actually changes crop when motion != hold;
5. ASR/text integrity can be checked by the existing skill flow.

No critic registry, provenance framework, pattern lifecycle, director provider, retention gate, or complex report schema in v1.7 Lite.

## Definition of done

- `zoom_planner.py` produces a valid plan from observations + semantic events;
- 1–3 feasible states work automatically;
- WHY is independent from gaze;
- blink/blur/gesture safety is preserved;
- renderer accepts canonical crop coordinates;
- simple QC catches invalid crops and no-op zooms;
- implementation stays small enough to understand and modify directly.
