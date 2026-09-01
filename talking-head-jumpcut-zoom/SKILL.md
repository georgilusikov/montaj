---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head видео (9:16, Shorts, Reels, TikTok) по архитектуре v1.7.2 Lite: normalize → speech_cleanup → visual_scan → agent semantic WHY → semantic_events → zoom_planner → QC → visual evidence review → pipeline guard → render → pixel QC → final visual review. Triggers: "смонтируй говорящую голову", "talking head zoom", "сделай зумы как в рилс", "подрежь паузы и расставь зумы", "автомонтаж shorts", "zoom_planner", "ratchet zoom".'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.2 Lite

**Goal:** deterministic talking-head editing where the agent chooses editorial meaning, canonical scripts own timing/rendering, and every claim about the actual video has visual evidence.

Core invariant:

```text
CONTENT / PACING != SEMANTIC FRAMING != VISUAL EVIDENCE
```

- pauses and content jumpcuts belong to pacing;
- zoom/reframe exists only because meaning justifies it;
- visual safety/aesthetic claims require machine perception or actually inspected frames.

---

## 0. CANONICAL PIPELINE LOCK — highest priority

For a production run the canonical scripts are mandatory.

**Never create replacement production scripts** such as:

```text
run_full_montage.py
fast_montage.py
segment_montage.py
build_analysis.py
new_zoom_planner.py
custom_renderer.py
```

when an equivalent canonical stage already exists.

If a canonical step fails:

```text
STOP → diagnose the canonical step → fix/use the canonical step → rerun
```

Do **not** silently bypass it with an ad-hoc implementation.

`render_zoom.py` is machine-locked: production CLI rendering requires a PASS receipt from `pipeline_guard.py pre-render`.

`--unsafe-bypass-pipeline-lock` is for tests/debug only and is forbidden in production skill execution.

### Scope lock

This skill owns:

- source normalization;
- strict speech cleanup / jumpcuts;
- visual observations for crop/cut safety;
- semantic zoom planning;
- zoom rendering;
- QC.

It may export SRT captions, but it does **not** invent a subtitle graphics pipeline during a zoom run. If a separate canonical subtitle renderer is not available/requested, do not create looped PNG overlays or a new subtitle compositor.

---

## 1. Mandatory production pipeline

```text
1. normalize_source.py
        ↓ normalized.mp4

2. Whisper word timings
        ↓ raw words

3. speech_cleanup.py
        ↓ cleanup_plan.json + dense.mp4 + output_words + content_cuts_ms

4. visual_scan.py
        ↓ visual_scan.json + observations
        machine perception of dense.mp4

5. AGENT SEMANTIC PASS — WHY ONLY
        ↓ semantic_marks.json

6. semantic_events.py
        ↓ semantic_events.json
        word spans → exact dense-timeline ms + boundary candidates

7. assemble analysis.json
        ↓ source + observations + semantic_events + content_cuts_ms

8. zoom_planner.py
        ↓ zoom_plan.json

9. simple_qc.py --output-json pre_qc.json
        ↓ MUST PASS

10. visual_evidence.py dense.mp4 ... --phase pre
        ↓ pre_visual/visual_evidence.json + extracted JPGs

11. AGENT/HUMAN VISUAL REVIEW
        ↓ pre_visual_review.json
        agent MUST actually open the extracted images

12. pipeline_guard.py pre-render
        ↓ pre_guard.json MUST PASS

13. render_zoom.py --guard-report pre_guard.json
        ↓ final.mp4

14. post_render_qc.py --output-json post_qc.json
        ↓ actual-pixel QC MUST PASS

15. visual_evidence.py final.mp4 ... --phase final
        ↓ final_visual/visual_evidence.json + extracted JPGs

16. AGENT/HUMAN FINAL VISUAL REVIEW
        ↓ final_visual_review.json

17. pipeline_guard.py final
        ↓ final_guard.json MUST PASS
        ↓ accepted final
```

No omitted mandatory stage may be described as a successful production run.

---

## 2. What it means for the agent to "watch" the video

Do not say or imply "I watched/checked the video" merely because you ran:

```text
ffprobe
Whisper
RMS/silence detection
JSON inspection
```

Those tools do not inspect visual content.

There are two valid visual evidence paths:

### A. Machine perception — full timeline sampling

`visual_scan.py` samples `dense.mp4` and measures:

- face bbox / center / size;
- eye line when available;
- EAR/MAR when MediaPipe FaceMesh is available;
- Laplacian blur;
- optical-flow motion;
- hard visual rejection when face detection fails or quality is unsafe.

Backend order:

```text
MediaPipe FaceMesh if available
        ↓ fallback
OpenCV Haar face detection
```

Default scan is lightweight (~6 samples/s), not every decoded frame sent to an LLM.

If face coverage is below 70%, the scan fails closed by default. Do not replace missing visual evidence with assumptions.

### B. Actual vision review — selected frames

`visual_evidence.py` extracts `-160 / 0 / +160 ms` frames around:

- every content jumpcut;
- every visible semantic zoom/reframe;
- every return-to-context framing change.

A vision-capable agent or human must **open these images** and write a review receipt.

Example receipt:

```json
{
  "status": "PASS",
  "reviewer": "vision_model",
  "reviewed_groups": [
    {
      "id": "zoom_00018200",
      "verdict": "PASS",
      "notes": "face remains stable; reframe does not cut gesture"
    }
  ]
}
```

Do not fabricate the receipt from filenames/metadata without viewing the images.

---

## 3. Phase 1 — speech cleanup

`speech_cleanup.py` owns pacing.

Default strict policy:

- pauses `<= 500 ms` preserved;
- pauses `> 500 ms` reduced to about `180 ms`;
- about `120 ms` head pad;
- about `350 ms` tail pad;
- short audio fades around hard cuts;
- strict mode does not remove fillers, false starts or spoken words.

Output includes:

- `kept_segments`;
- `removed_gaps`;
- `content_cuts_ms`;
- `output_words` remapped to the dense timeline;
- optional `dense.mp4` and SRT.

The **dense timeline is canonical** for all later timestamps.

Do not replace word-timing cleanup with a custom RMS-only silence cutter. RMS can be auxiliary evidence, not the canonical edit decision source.

---

## 4. Semantic Director — agent owns WHY, not milliseconds

The agent reads `output_words` and creates semantic marks.

Required per mark:

```json
{
  "start_word": 12,
  "end_word": 20,
  "importance": 0.78,
  "why": "important correction of the viewer's assumption"
}
```

Optional:

- `direction`: `build|peak|release|neutral|ratchet_1|ratchet_2|ratchet_3`;
- `motion_hint`: `auto|step|slow_push`;
- `zoom_duration_type`: `micro_punch|beat|argument_hold`.

`semantic_events.py` owns exact timing and boundary candidates.

For spoken span >=8 s, empty semantic marks fail by default. Intentional editorial no-zoom requires the explicit override and must not hide a failed semantic pass.

### Valid WHY

- hook / contrarian thesis;
- antithesis or correction;
- important rule/number;
- warning/consequence;
- argument change;
- example → conclusion;
- punchline/conclusion;
- explicit list escalation.

Not WHY by itself:

- elapsed time;
- gaze/head return;
- jumpcut occurrence;
- "it has been a while since the last zoom".

---

## 5. Visual vocabulary

Default moderate:

```text
CONTEXT     1.00x       exact source frame / home
ARGUMENT    ~1.10–1.12
EMPHASIS    ~1.16
dynamic EMPHASIS hard cap 1.20
```

Actual scale is constrained by:

- measured face size;
- crop geometry;
- quality cap;
- style cap;
- state cap;
- crop safety.

4K resolution gives quality headroom, not permission for artistically stronger zoom.

---

## 6. Motion and WHEN

Primary language:

- `step` — default semantic reframe;
- `slow_push` — rare and explicit;
- `hold` — no framing change.

Typical temporary episode lengths:

- `micro_punch`: 0.8–1.4 s;
- `beat`: 1.5–2.4 s;
- `argument_hold`: 2.5–3.5 s.

Normally return to exact CONTEXT after the episode.

Hard reject transition points with visual evidence of:

- blink / long eye closure;
- mouth distortion;
- blur;
- unsafe head pose / strong turn;
- hard gesture or prop conflict;
- unsafe crop / face travel / headroom.

Soft bonuses:

- semantic proximity;
- word boundary;
- pause;
- head return;
- cadence fit.

### Tripod Lock

Crop center is fixed during a hold. No per-frame face chasing.

### Eye anchor for slow push

```text
Delta_Y = (Y_eyes - Y_center) * (1 - 1/scale)
```

---

## 7. Visual rhythm

```text
visual refresh every ~2–5 s != zoom every ~2–5 s
```

`content_cuts_ms` already count as visual refreshes.

If a long visual gap remains, planner may request:

```json
{
  "preferred_action": "jumpcut_same_scale",
  "fallback_action": "hold_if_no_safe_cut",
  "semantic_trigger": false,
  "why": "visual_refresh_gap"
}
```

Cadence never creates fake semantic WHY.

---

## 8. QC and evidence gates

### Pre-render plan QC

`simple_qc.py` fails on:

- missing semantic decisions on a long edit;
- zero visible framing changes when semantics require them;
- ARGUMENT/EMPHASIS intent collapsing to a no-op;
- invalid crop/scale/cap geometry.

Persist the receipt:

```bash
python scripts/simple_qc.py zoom_plan.json --output-json pre_qc.json
```

### Pre-render visual gate

Generate evidence:

```bash
python scripts/visual_evidence.py dense.mp4 zoom_plan.json pre_visual \
  --cleanup-plan cleanup_plan.json --phase pre
```

Open the extracted images and create `pre_visual_review.json`.

Then:

```bash
python scripts/pipeline_guard.py pre-render \
  --cleanup cleanup_plan.json \
  --semantic semantic_events.json \
  --visual-scan visual_scan.json \
  --zoom-plan zoom_plan.json \
  --pre-qc pre_qc.json \
  --visual-manifest pre_visual/visual_evidence.json \
  --visual-review pre_visual_review.json \
  --output-json pre_guard.json
```

Only PASS may render.

### Post-render pixel QC

```bash
python scripts/post_render_qc.py dense.mp4 final.mp4 zoom_plan.json \
  --output-json post_qc.json
```

This compares expected crop pixels to the actual artifact and catches:

```text
zoom_plan says 1.12x
BUT final.mp4 stayed at 1.00x
```

### Final visual acceptance

```bash
python scripts/visual_evidence.py final.mp4 zoom_plan.json final_visual \
  --cleanup-plan cleanup_plan.json --phase final
```

Actually inspect the final extracted images, produce `final_visual_review.json`, then:

```bash
python scripts/pipeline_guard.py final \
  --pre-guard pre_guard.json \
  --post-qc post_qc.json \
  --visual-manifest final_visual/visual_evidence.json \
  --visual-review final_visual_review.json \
  --output-json final_guard.json
```

Only `accepted_final=true` is a production success.

---

## 9. Render performance rules

Use the canonical `render_zoom.py`; do not react to slow rendering by inventing a replacement renderer.

Production command:

```bash
python scripts/render_zoom.py dense.mp4 zoom_plan.json final.mp4 \
  --guard-report pre_guard.json \
  --encoder-preset fast
```

The renderer exposes FFmpeg `-progress` directly. **Do not capture or hide stderr/progress** and then estimate completion from output file size.

Do not claim "90% complete" unless progress data supports it.

Avoid in ad-hoc code:

- looped image inputs without explicit bounded duration;
- dozens of PNG overlay inputs for captions;
- repeated independent decoding of the same 4K source;
- `libx264 -preset slow` for ordinary iteration.

`concat -c copy` only avoids an additional encode at concat time; it does not make already encoded segments lossless.

---

## 10. Canonical commands summary

```bash
python scripts/normalize_source.py raw.mp4 normalized.mp4

python scripts/speech_cleanup.py speech_input.json cleanup_plan.json \
  --input-video normalized.mp4 --output-video dense.mp4 --export-srt captions.srt

python scripts/visual_scan.py dense.mp4 visual_scan.json

python scripts/semantic_events.py semantic_input.json semantic_events.json

# analysis.json = source + visual_scan.observations + semantic_events + content_cuts_ms
python scripts/zoom_planner.py analysis.json zoom_plan.json

python scripts/simple_qc.py zoom_plan.json --output-json pre_qc.json

python scripts/visual_evidence.py dense.mp4 zoom_plan.json pre_visual \
  --cleanup-plan cleanup_plan.json --phase pre
# OPEN FRAMES → write pre_visual_review.json

python scripts/pipeline_guard.py pre-render \
  --cleanup cleanup_plan.json --semantic semantic_events.json \
  --visual-scan visual_scan.json --zoom-plan zoom_plan.json \
  --pre-qc pre_qc.json --visual-manifest pre_visual/visual_evidence.json \
  --visual-review pre_visual_review.json --output-json pre_guard.json

python scripts/render_zoom.py dense.mp4 zoom_plan.json final.mp4 --guard-report pre_guard.json

python scripts/post_render_qc.py dense.mp4 final.mp4 zoom_plan.json --output-json post_qc.json

python scripts/visual_evidence.py final.mp4 zoom_plan.json final_visual \
  --cleanup-plan cleanup_plan.json --phase final
# OPEN FRAMES → write final_visual_review.json

python scripts/pipeline_guard.py final \
  --pre-guard pre_guard.json --post-qc post_qc.json \
  --visual-manifest final_visual/visual_evidence.json \
  --visual-review final_visual_review.json --output-json final_guard.json
```

Acceptance condition:

```text
canonical stages present
AND semantic contract valid
AND machine visual scan valid
AND pre-render QC PASS
AND pre-render frames actually visually reviewed
AND pipeline guard PASS
AND canonical render completed
AND post-render pixel QC PASS
AND final frames actually visually reviewed
AND final guard PASS
```
