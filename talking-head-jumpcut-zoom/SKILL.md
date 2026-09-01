---
name: talking-head-jumpcut-zoom
description: 'Автомонтаж вертикальных talking-head видео (9:16, Shorts, Reels, TikTok) по архитектуре v1.7.5 Lite: normalize → Whisper → speech_cleanup with executable family gate → visual_scan → semantic WHY + bounded performance salience → semantic_events → zoom_planner → QC → visual evidence → guarded render → pixel QC → final visual review. Triggers: "смонтируй говорящую голову", "talking head zoom", "сделай зумы как в рилс", "подрежь паузы и расставь зумы", "автомонтаж shorts", "zoom_planner", "ratchet zoom".'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.5 Lite

**Goal:** keep the reliability of v1.7.2 while restoring the restrained, performance-aware directing feel of the early v1.x editor.

Core invariant:

```text
CONTENT / PACING != SEMANTIC FRAMING != VISUAL EVIDENCE
```

And one additional v1.7.5 rule:

```text
WHAT was said + HOW it was delivered -> editorial salience
BUT performance alone never creates WHY.
```

---

## 0. Canonical pipeline lock

For production, canonical scripts are mandatory. Never create replacement production scripts such as:

```text
run_full_montage.py
fast_montage.py
segment_montage.py
build_analysis.py
new_zoom_planner.py
custom_renderer.py
```

If a canonical stage fails:

```text
STOP -> diagnose/fix that stage -> rerun it
```

Do not bypass it with ad-hoc code.

`render_zoom.py` requires a PASS receipt from `pipeline_guard.py pre-render`. `--unsafe-bypass-pipeline-lock` is debug/test only.

---

## 1. Mandatory production pipeline

```text
1. normalize_source.py
        ↓ normalized.mp4

2. Whisper word timings
        ↓ raw words

3. speech_cleanup.py
        ↓ executable FAMILY GATE A/B/C
        ↓ cleanup_plan.json + dense.mp4 + output_words + content_cuts_ms

4. visual_scan.py
        ↓ visual_scan.json + observations

5. AGENT SEMANTIC PASS
        ↓ semantic_marks.json
        WHY + optional bounded performance evidence

6. semantic_events.py
        ↓ exact dense-timeline semantic_events.json

7. assemble analysis.json
        ↓ source + observations + semantic_events + content_cuts_ms

8. zoom_planner.py
        ↓ zoom_plan.json

9. simple_qc.py --output-json pre_qc.json
        ↓ MUST PASS

10. visual_evidence.py dense.mp4 ... --phase pre
        ↓ extracted real frames

11. AGENT/HUMAN VISUAL REVIEW
        ↓ pre_visual_review.json

12. pipeline_guard.py pre-render
        ↓ pre_guard.json MUST PASS

13. render_zoom.py --guard-report pre_guard.json
        ↓ final.mp4

14. post_render_qc.py --output-json post_qc.json
        ↓ actual-pixel QC MUST PASS

15. visual_evidence.py final.mp4 ... --phase final
        ↓ final frames

16. AGENT/HUMAN FINAL VISUAL REVIEW
        ↓ final_visual_review.json

17. pipeline_guard.py final
        ↓ final_guard.json MUST PASS
```

No omitted mandatory stage may be described as a successful production run.

---

## 2. What counts as watching the video

These do **not** count as visual review:

```text
ffprobe
Whisper
RMS/silence detection
JSON inspection
```

Valid visual evidence has two layers:

### Machine perception

`visual_scan.py` samples the actual dense video and measures face geometry, eye line when available, blur, motion and crop-safety signals. MediaPipe FaceMesh is preferred; OpenCV face detection is fallback.

### Actual selected-frame review

`visual_evidence.py` extracts frames around every content jumpcut, visible semantic reframe and return-to-context change. A vision-capable agent or human must open those images and write the review receipt.

Do not fabricate review receipts from filenames or metadata.

---

## 3. Pacing: executable family gate

The old v1.7.4 error was making `250 ms` a global default while family classification existed only in prose. v1.7.5 moves the gate into `speech_cleanup.py`.

### Family A — dense

Recognize conservatively from RAW word gaps. If AUTO is ambiguous, choose A.

Default:

```text
pause_cleanup_enabled = false
```

Do not create jumpcuts merely for cadence. Dense speech can have zero `content_cuts_ms`.

### Family B — air

Repeated real gaps trigger Family B. Canonical default:

```text
cut_threshold_ms = 250
target_gap_ms = 180
```

Strict cleanup removes dead air only; never words, fillers or false starts.

### Family C — explicit second-take / CTA case

C is owner-supplied, not guessed from taste. Body cleanup is off by default. Do not invent a CTA or a second take.

### Fail-safe AUTO classifier

AUTO chooses B only with repeated air:

```text
>= 2 gaps > 450 ms
OR
>= 4 gaps > 300 ms
```

Otherwise A.

One isolated long pause is ambiguous and stays A unless the user/config explicitly requests cleanup.

### Acoustic refinement

v1.7.4 mentioned RMS/VAD correction but had no canonical implementation. v1.7.5 explicitly **does not improvise** one. Until a tested acoustic boundary detector exists, word timings remain authoritative. Do not create a custom RMS cutter during production.

---

## 4. Semantic Director: WHY first, performance only amplifies

The agent owns semantic marks, not milliseconds.

Required:

```json
{
  "start_word": 10,
  "end_word": 16,
  "importance": 0.72,
  "why": "main contrast / thesis payoff"
}
```

Optional:

```json
{
  "direction": "build|peak|release|neutral|ratchet_1|ratchet_2|ratchet_3",
  "motion_hint": "auto|step|slow_push",
  "zoom_duration_type": "micro_punch|beat|argument_hold",
  "performance_emphasis": 0.85,
  "performance_evidence": "speaker leans toward camera and delivery energy rises"
}
```

### Valid WHY

Typical semantic marks:

- thesis after setup;
- antithesis/correction;
- payoff after a number/formula;
- warning/consequence;
- conclusion/punchline;
- explicit list escalation;
- example -> conclusion.

Not WHY by itself:

- elapsed time;
- gaze/head return;
- a jumpcut;
- bare number;
- setup/bridge line;
- CTA/link-in-bio;
- “it has been a while since the last zoom”.

Opening setup and closing CTA are normally exact home `1.00x` unless their content is itself the thesis/payoff.

### Performance-aware salience

Early v1.x benefited from HOW the speaker delivered a line. v1.7.5 restores that only as a bounded amplifier.

Rules:

1. performance never creates a mark;
2. semantic `importance < 0.40` gets **zero** performance bonus;
3. performance must include evidence from actual visual/prosodic inspection;
4. maximum bonus is `+0.08 importance`;
5. gaze or head motion by itself is not a reason.

So:

```text
semantic 0.80 + strong delivery -> at most 0.88
semantic 0.30 + dramatic head move -> remains 0.30
```

This lets HOW strengthen WHAT without returning to random movement-driven zooms.

---

## 5. Gold-lite visual language

The v1.7.4 scale reduction is retained and made more conservative.

```text
CONTEXT     1.00x  exact source/home; majority of runtime
ARGUMENT    1.08x  normal semantic punch
EMPHASIS    1.12x  strong peak
RATCHET_1   1.08x
RATCHET_2   1.12x
RATCHET_3   1.13x  explicit list climax only
ABS HARD CAP 1.13x
```

`ARGUMENT` is **1.08**, not “1.06–1.10”. Geometry may reduce a requested scale, never silently enlarge it above the state/style/global cap. Source resolution never raises the artistic hard cap above `1.13x`.

Actual crop still obeys:

- source geometry;
- face size/travel;
- **segment-wide headroom >= 5%**;
- quality cap;
- state/style cap;
- gesture/prop/caption safety.

### Restored segment-wide headroom invariant

Headroom is an active composition rule, not merely an emergency rejection after the crop is chosen.

For every visible framing episode, sample `hair_top` across the whole anticipated shot and use the highest head position:

```text
hair_top_segment = min(hair_top[t] across the framing episode)
required_headroom = 0.05 * crop_height
Y_crop = min(Y_eye_anchor, hair_top_segment_px - required_headroom)
```

Then clamp the crop to source bounds and run normal face/gesture safety checks.

Meaning:

- keep at least about **5% of output-frame height above the hair** throughout the shot;
- if the desired zoom cannot preserve that air, prefer a smaller zoom or no zoom;
- eye-line anchoring remains useful, but headroom has priority when the two conflict;
- do not chase the face per frame: Tripod Lock still applies within the episode.

4K resolution does not automatically justify a stronger artistic zoom.

---

## 6. Motion and dramatic episodes

Primary language:

- `step` — normal semantic punch;
- `slow_push` — rare, explicit build;
- `hold` — no framing change.

Gold-lite durations:

```text
micro_punch     0.5–1.2 s
beat            1.2–2.0 s
argument_hold   2.0–2.5 s, rare
```

### Do not create zoom chatter

The old wording “prefer many short punches” was too easy to interpret as repeated `home -> punch -> home` chatter.

v1.7.5 rule:

```text
new semantic block / release -> reset to CONTEXT
same coherent build -> peak episode -> may sustain tension without flashing home
```

Examples:

```text
GOOD: 1.00 -> 1.08 build -> 1.12 peak -> 1.00 release
GOOD: 1.00 -> short 1.08 punch -> 1.00
BAD:  1.00 -> 1.08 -> 1.00 -> 1.08 -> 1.00 every clause
```

The planner's continuation/return logic should preserve a coherent episode when adjacent semantic beats belong to the same thought.

---

## 7. Density is a ceiling, never a target

Gold references roughly support an upper density around one visible semantic punch per ~7 s averaged across a dense take.

This is **not a quota** and never creates WHY.

```text
~1 / 7 s = observational ceiling / warning signal
NOT desired zoom cadence
```

A 100-second video may legitimately have 5, 8, 12 or fewer punches depending on meaning. Never manufacture events to reach a count.

Visual refresh can also come from real content jumpcuts or a separate caption system. Do not create fake pause cuts or fake zooms merely to refresh the frame.

---

## 8. WHEN: safety first

Semantic WHY chooses what deserves an accent. Boundary selection chooses when it is safe.

Hard reject transition points with:

- blink/eye closure;
- unsafe blur;
- distorted mouth/face;
- unsafe head pose/turn;
- gesture/prop collision;
- crop/headroom/face-travel violation.

Soft bonuses may include:

- nearby word boundary;
- pause;
- head return;
- cadence fit.

Gaze/head return may improve WHEN but never manufacture WHY.

Tripod Lock remains mandatory inside a hold/episode: do not frame-track the speaker every frame.

---

## 9. QC and acceptance

Pre-render `simple_qc.py` remains fail-closed for:

- missing semantics on a normal spoken edit;
- zero visible framing when semantics expect it;
- semantic ARGUMENT/EMPHASIS collapsing to a silent no-op;
- invalid/excessive state scale;
- declared headroom below the 5% composition floor.

`pipeline_guard.py pre-render` additionally requires:

- cleanup provenance;
- executable family A/B/C provenance;
- visual observations;
- semantic events;
- zoom plan + pre-QC PASS;
- complete real visual-review receipt.

Post-render acceptance requires:

- actual-pixel `post_render_qc.py` PASS;
- final extracted-frame visual review;
- `pipeline_guard.py final` PASS.

Valid JSON is never proof that the MP4 contains the planned crop.

---

## 10. Canonical ownership

```text
speech_cleanup.py   -> family + pacing
semantic agent      -> WHY + optional performance evidence
semantic_events.py  -> deterministic timing + bounded performance bonus
visual_scan.py      -> machine visual observations
zoom_planner.py     -> feasible state / timing / crop / motion
render_zoom.py      -> render only the plan
QC/guards           -> acceptance evidence
```

No layer should silently take over another layer's job.

---

## 11. Definition of done for v1.7.5

- Family A/B/C is executable, not prose-only.
- 250 ms is Family-B policy, not a global default.
- Ambiguous AUTO pacing fails safe to A.
- No unimplemented RMS/VAD instruction invites ad-hoc cutters.
- Normal punch is canonical 1.08; strong peak 1.12; ratchet climax max 1.13; **nothing exceeds 1.13x**.
- Every visible crop preserves **>=5% segment-wide headroom** when `hair_top` evidence is available.
- Performance can amplify semantic salience but cannot create semantic events.
- Punch density is a ceiling, never a quota.
- Coherent build->peak episodes may sustain tension without home-frame chatter.
- Setup/bridge/CTA stay home unless meaning independently justifies an accent.
- Canonical pipeline lock, visual evidence and post-render QC remain intact.
