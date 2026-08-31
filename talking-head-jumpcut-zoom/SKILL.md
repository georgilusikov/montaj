---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикального talking-head видео: сначала strict speech cleanup удаляет длинные паузы и создаёт плотный jumpcut timeline, затем semantic zoom planner расставляет смысловые reframes/zooms. CONTEXT=1.00x, ARGUMENT≈1.10–1.12x, EMPHASIS≈1.16–1.20x. Triggers: "подрежь паузы и расставь зумы", "talking head jumpcut zoom", "автомонтаж reels/shorts", "semantic zoom".'
---

# Talking-Head Jumpcut & Zoom Editor v1.7 Lite

Это **маленький двухфазный skill**, а не монтажный framework.

Главный закон:

```text
CONTENT / PACING first
SEMANTIC FRAMING second
```

Зум не должен компенсировать необрезанные паузы.

## 1. Canonical pipeline

```text
normalized source
  ↓
Whisper word-level timings
  ↓
scripts/speech_cleanup.py
  ↓
cleanup_plan.json + dense.mp4 + output_words + content_cuts_ms
  ↓
perception + semantic analysis on dense timeline
  ↓
analysis.json
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

Subtitles are generated externally and are not part of camera cadence.

---

## 2. Phase 1 — strict speech cleanup / jumpcuts

Use `scripts/speech_cleanup.py` before zoom planning.

Purpose: remove dead air while preserving every spoken word.

### Default strict policy

```text
pause <= 500 ms        keep
pause > 500 ms         reduce to ~180 ms
head before first word ~120 ms
tail after last word   ~350 ms
audio edge fade        15 ms
```

Do not remove fillers, repetitions, false starts or words in Lite `strict` mode.

Example input:

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
    {"text": "Nunca", "start_ms": 320, "end_ms": 610}
  ]
}
```

Run plan only:

```bash
python scripts/speech_cleanup.py speech_input.json cleanup_plan.json
```

Plan + render dense video:

```bash
python scripts/speech_cleanup.py speech_input.json cleanup_plan.json \
  --input-video normalized.mp4 \
  --output-video dense.mp4
```

`cleanup_plan.json` provides:

- `kept_segments`: source→output mapping;
- `content_cuts_ms`: jumpcuts on dense output timeline;
- `removed_gaps`: audit of removed silence;
- `output_words`: original words remapped to dense output time.

**All later semantic/framing decisions use the dense output timeline.** Do not mix source timestamps with dense output timestamps.

---

## 3. Phase 2 — semantic framing

Core logic:

```text
WHY → CAN → WHEN → MOTION → DURATION → RETURN
```

### WHY

Zoom reason comes from meaning, not cadence, gaze or head movement.

Importance defaults:

```text
< 0.40        CONTEXT
0.40–0.84     ARGUMENT
>= 0.85       EMPHASIS
```

Directions:

- `build` — tension rises;
- `peak` — strongest justified beat;
- `release` — return home;
- `neutral` — hold.

Useful semantic triggers: antithesis, change of subject, warning, key number/rule, quote/axiom, conclusion, punchline.

Do not implement language keywords as Python rules. The semantic layer decides WHY.

### CAN / framing states

Default moderate visual grammar:

```text
CONTEXT    = 1.00x exact source frame
ARGUMENT   = ~1.10–1.12x
EMPHASIS   = ~1.16x, dynamic may reach 1.20x
```

Actual crop is computed from source composition and temporal geometry. If a state is unsafe or visually redundant, downgrade/collapse it.

Hard artistic cap: `1.20x` even if 4K quality would allow more.

### WHEN

Reject transition points with:

- blink / long eye closure;
- blur;
- strong unsafe head turn / pose;
- hard gesture or prop conflict;
- unsafe crop geometry.

Prefer:

- semantic/clause boundary;
- word boundary;
- pause;
- head return;
- good camera rhythm.

Gaze/head return may improve WHEN but never create WHY.

---

## 4. Motion language

### Default semantic punch = step/reframe

```text
1.00 → 1.12 → 1.00
```

Normal ARGUMENT and EMPHASIS use a clean discrete reframe on a safe semantic boundary.

### Rare gradual build

Slow push is not automatic.

The semantic event must explicitly request:

```json
{"direction":"build", "motion_hint":"slow_push"}
```

Typical moderate build:

```text
1.00 ── 1.5–3.0 s ──→ ~1.05
```

It may then escalate to a real ARGUMENT/EMPHASIS punch.

Slow push rendering uses dense 60 Hz easing. Do not use the old 10 Hz stair-step interpolation.

---

## 5. Zoom episode duration

Close framing is a temporary semantic episode, not a persistent state.

```text
micro_punch     0.8–1.4 s
beat            1.5–2.4 s
argument_hold   2.5–3.5 s
```

Infer from semantic-clause duration unless explicitly supplied.

After ARGUMENT/EMPHASIS, normally return to CONTEXT 1.00x.

Closely connected `build → peak` may stay close instead of flashing back to base for one frame.

Duration bands are guidance. Do not deliberately auto-return in the middle of an unsafe gesture if a nearby safe clause/pose boundary exists.

---

## 6. Visual cadence: 2–5 seconds

Target:

```text
some meaningful visual refresh roughly every 2–5 s
```

But:

```text
visual refresh ≠ zoom
```

Primary cadence source is Phase 1 jumpcuts.

`zoom_planner.py` receives `content_cuts_ms` from cleanup. It combines those cuts with semantic framing changes.

If a >5 s visual gap remains, planner emits `cadence_requests`:

```json
{
  "preferred_action": "jumpcut_same_scale",
  "fallback_action": "hold_if_no_safe_cut",
  "semantic_trigger": false,
  "why": "visual_refresh_gap"
}
```

These are content-cut requests, **not camera motions**.

Do not manufacture an ambient `1.00 ↔ 1.05` breathing loop. That watchdog is removed.

---

## 7. Renderer contract

`render_zoom.py` receives the already-dense video produced by Phase 1.

It executes only:

- semantic `decisions`;
- explicit `returns` to CONTEXT.

It does not re-solve crop geometry and does not convert cadence requests into fake zooms.

Canonical crop coordinates come from the planner.

---

## 8. QC Lite

Before accepting output verify:

1. speech cleanup did not delete spoken words;
2. `kept_segments` are contiguous on output timeline;
3. `output_words` remain ordered;
4. content cuts are on dense output time;
5. crop remains inside source;
6. CONTEXT is exact 1.00x source frame;
7. ARGUMENT/EMPHASIS respect caps;
8. non-hold motion changes crop;
9. strong crop does not cut face/hair/critical gesture;
10. cadence requests remain non-semantic.

If post-render review reveals long silent stretches, fix Phase 1 first. Do not increase zoom count to hide dead air.

---

## 9. Definition of done

A correct Lite edit has this order:

```text
raw/normalized video
→ strict pause cleanup
→ dense jumpcut video
→ semantic analysis
→ semantic zoom episodes
→ render
→ QC
```

Expected visual language:

```text
1.00 = home / air
~1.12 = common semantic punch
~1.16–1.20 = rare climax
rare ~1.05 slow build = gradual tension
```

The result should feel rhythmically alive because **content cuts carry pacing and zoom carries meaning**.

For implementation details and JSON contracts, see `V1_7_LITE.md`.
