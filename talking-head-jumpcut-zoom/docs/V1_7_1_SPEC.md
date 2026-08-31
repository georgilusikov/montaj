# Talking-Head Jumpcut & Zoom Editor v1.7.1
## Semantic Zoom Planner — Final Implementation Specification

**Status:** implementation-ready  
**Date:** 2026-08-31  
**Target:** migrate the working v1.6.2 behavior into a deterministic semantic framing planner.  
**Repository note:** public `main` currently identifies the skill as v1.5 and mixes later v1.6 notes/roadmap. Any rule named below that is absent from `main` is a migration point from the working v1.6.2 baseline, not a claim about current `main`.

---

## 0. Goal and non-goals

v1.7.1 replaces locally competing zoom rules with one pipeline:

`PERCEPTION → TEMPORAL FEASIBILITY → SEMANTICS/WHY → DESIRED STATE → PATTERN SCORE → WHEN → MOTION INTENT → CANONICAL FRAMING → RENDER → INDEPENDENT QC`

Goals:
1. Zooms/reframes are caused by meaning, not gaze or cadence alone.
2. Framing is derived from the actual source composition, not fixed `1.00/1.08/1.16 = wide/medium/close` assumptions.
3. Planner and critic must not disagree because of impossible shot targets.
4. Temporal feasibility prevents geometry from being computed on a segment that has not been chosen yet.
5. The deterministic planner must produce byte-stable canonical output for frozen inputs.
6. Mechanical QC remains independent from artistic review.

Non-goals:
- scale `<1.00` without padding/generative expansion;
- free-form LLM zoom curves;
- hard retention gate before calibration;
- automatic aggressive zoom because input is 4K;
- changing AI-avatar forced cadence `2.0–4.0s`;
- replacing speech-integrity, blink, blur, prop, loop, audio or provenance protections.

---

## 1. Architectural boundaries

### 1.1 Perception / `analysis.json`
Contains observations and evidence only. It MUST NOT contain planner policy decisions such as `quality_cap`, `pattern_score`, selected shot state or final crop.

Examples of valid analysis facts:
- resolution/fps/colorspace;
- sharpness/noise/compression metrics;
- face track, hair top, face ratio distribution;
- head pose and `head_facing_camera` proxy;
- blink/eye-closure/blur intervals;
- gesture and prop intervals;
- caption/UI hard zones;
- artifact score for AI avatars;
- ASR, pauses, breaths, prosody;
- salience evidence, acts, theme probabilities/priors with provenance.

### 1.2 Semantic layer / `thz_semantics`
May use LLM + deterministic probes, but does NOT write timeline decisions.
Outputs annotations with provenance:
- acts;
- salience hits;
- prosody peaks;
- theme probabilities/priors;
- semantic weights.

Required provenance:
`model_id`, `model_revision`, `temperature`, `prompt_version`, `semantics_version`, input hash.

### 1.3 Deterministic planner / `thz_planner`
Consumes frozen analysis + config and owns all policy decisions:
- caps;
- temporal feasibility map;
- feasible shot states;
- WHY/desired state;
- pattern score;
- WHEN boundary selection;
- motion intent;
- canonical framing.

### 1.4 Content edit vs framing edit
Keep two formal planes:

**CONTENT EDIT**
- keep/remove source intervals;
- hard cuts that remove footage;
- speech integrity and source/out timestamp mapping.

**FRAMING PLANNER**
- shot states;
- reframes;
- crop/anchor decisions;
- drift/ramp motion.

The WHEN solver may coordinate their boundaries, but a hard cut is not a kind of semantic zoom.

### 1.5 Renderer
Renderer executes canonical framing only. It must not infer crop/anchor policy from scale alone.

### 1.6 Independent critic
Post-render critic MUST independently measure the rendered master. It must not reuse planner geometry code for `COMPOSITION_SAFE` or rendered framing verification.

---

## 2. Naming migration

Canonical terminology:

| Old | v1.7.1 |
|---|---|
| plan1 | `CONTEXT` |
| plan2 | `ARGUMENT` |
| plan3 | `EMPHASIS` |
| plan1/2/3_share | `state_share.context/argument/emphasis` |
| plan3_distribution | `emphasis_distribution` |
| scale_cap | `quality_cap_prior` / resolved `quality_cap` |
| intensity cap | `style_cap` |
| framing targets | provisional `desired_face_bands` |
| at_camera | `head_facing_camera` proxy |
| semantic_hold | `semantic_push` |
| old priority list | `WHY + WHEN` |
| intensity_floor | removed; optional `wide_boost` replaces it |

No new implementation should introduce `plan1/plan2/plan3` fields.

---

## 3. Cap model

Final scale is constrained by separate concerns:

`actual_scale = min(desired_scale, quality_cap, style_cap, geometry_cap(window))`

### 3.1 Style cap
Default:
- calm: `1.10`
- moderate: `1.16`
- dynamic: `1.20`

The profile/intensity system remains the artistic cap source.

### 3.2 Quality cap
Resolution table is an upper-bound prior, not a lossless guarantee:
- 1080p prior upper bound: `1.25`
- 1440p: `1.40`
- 4K: `1.60`

The resolved cap must be reduced from the prior using measured sharpness/noise/compression. The first implementation may use a deterministic heuristic, but it must write metrics and reason codes to planner diagnostics.

Delete claims that 1080→1080 zoom above 1.00 is lossless.

### 3.3 Geometry cap
Geometry is temporal. There is no single geometry cap before boundaries exist. Planner must build feasibility over time/windows and derive a window-specific cap after WHEN selects a candidate interval.

### 3.4 Wide source
Remove `intensity_floor` if present in working v1.6.2.

Config:
`zoom.wide_boost=false` by default.

Without wide boost, `style_cap` remains active even on 4K.
With wide boost, planner may use a boosted style cap, but quality and geometry caps remain mandatory.

If source is too wide for target composition even after allowed boost, emit `wide_source_climax_weak` warning; do not invent an impossible state.

### 3.5 Scale lower bound
`scale >= 1.00` always.

---

## 4. Temporal composition model — P0

The planner must compute measurable composition features per sample/window before segment boundaries are finalized.

Minimum P0 measurements:
- `face_ratio_p05/p50/p95`;
- `face_center_x/y` distribution;
- top hair margin minimum;
- bottom must-keep margin minimum;
- left/right frame margins;
- caption hard-zone overlap;
- must-keep prop overlap/visibility;
- crop X/Y bounds;
- head pose proxy;
- hard gesture/hand-face exclusion windows where already available.

P1 may add richer aesthetic margins, shoulders/body composition and platform UI soft zones.

Do not store only booleans. Store measurements; booleans are derived from thresholds.

Example:
```json
{
  "top_margin_min": 0.061,
  "bottom_margin_min": 0.083,
  "caption_overlap_max": 0.0,
  "gesture_visibility_min": 0.94,
  "safe": true
}
```

---

## 5. Temporal feasibility map

This replaces precomputed segment-wide geometry before segments exist.

Canonical concept:
`feasible(state, time/window)`.

Example:
```text
EMPHASIS
  0–3100ms     feasible
  3100–4900ms  infeasible: hand_face_zone
  4900–7200ms  feasible
```

Implementation may represent this as intervals or sampled windows, but the planner must be able to answer:
- Is state S feasible at boundary t?
- Is state S feasible for window [a,b]?
- What is the max safe scale for [a,b]?
- Which constraint is limiting?

Blink and blur are NOT soft scores. They hard-mask candidate boundaries using legacy safety windows.

---

## 6. Feasible shot states

Semantic states:
- `CONTEXT`
- `ARGUMENT`
- `EMPHASIS`

Provisional desired face bands inherited as starting calibration values:
- CONTEXT: `0.26–0.34`
- ARGUMENT: `0.31–0.40`
- EMPHASIS: `0.38–0.44`

These are desired bands, not universal hard lower bounds.

For each candidate window:
1. derive desired scale from desired face composition;
2. apply caps;
3. compute actual face distribution (`p05/p50/p95`), not only median;
4. verify p95 hard maximum and composition hard zones;
5. create only distinguishable feasible states.

If three distinct states cannot exist:
- 2 states: `CONTEXT / EMPHASIS` or other best distinct pair;
- 1 state: static framing plus allowed motion intent.

No fake third state.

### 6.1 Distinctness
Do not use scale delta alone. Define `composition_distance` from normalized components such as:
- relative scale delta;
- face-ratio delta;
- face-center x/y delta.

The exact weights are provisional and calibration-owned. `delta_rel = abs(s2/s1 - 1)` remains the mechanical check for pure scale-step perceptibility.

---

## 7. WHY — semantic intent

WHY answers: should framing change now, and what state is desired?

Inputs:
- semantic weight;
- salience;
- prosody;
- act role;
- contrast/punchline;
- narrative progression.

Gaze/head return is not a reason for zoom.

Output is a state intent, e.g. `maintain`, `CONTEXT`, `ARGUMENT`, `EMPHASIS`, with reason/provenance.

---

## 8. Semantic analysis — TR-20/TR-21

TR-20 moves from roadmap to v1.7.1 after P0 contracts/geometry are stable.

Minimum salience evidence:
- numerals/amounts/percentages;
- repetition;
- contrast (`not X but Y`);
- warning/negation;
- causal conclusion;
- summary;
- strong claim;
- punchline.

Prosody features:
- pitch z-score;
- energy z-score;
- speech-rate change;
- pause before/after.

TR-21 creates acts and theme priors. Theme-to-pattern mapping is never hard.

`analysis.json` may store theme probabilities/semantic evidence, but final `pattern_prior` and `pattern_score` belong to planner diagnostics/timeline provenance.

---

## 9. Pattern scoring

Do not call this a posterior unless a probabilistic model is introduced. Canonical name: `PATTERN_SCORE`.

Pipeline:
1. hard-mask infeasible patterns;
2. score remaining patterns;
3. deterministic tie-break.

Initial form:
`score = w_theme*theme_prior + w_sem*semantic_fit + w_prosody*prosody_fit - w_history*history_penalty`

All components normalized to `[0,1]`; weights versioned and provisional.

Pattern metadata must declare:
- required number/type of states;
- `max_duration_ms`;
- `required_reset`;
- allowed terminal states.

If state availability is insufficient, pattern degrades deterministically instead of inventing states.

---

## 10. WHEN solver

WHEN searches only after desired state is known and uses temporal feasibility.

### Live profile
Candidate handling:
- semantic window / word boundary;
- head-return bonus when aligned with semantic emphasis;
- pause;
- gesture phase;
- breath soft guard;
- blink hard mask;
- blur hard mask;
- prop transition hard mask;
- eye-closure hard mask;
- overflow fallback.

Legacy `eye return + thesis = step +` becomes a boundary bonus, not a zoom cause.
Legacy overflow remains a WHEN fallback.

Until a real gaze model exists, `head_facing_camera` is the contact proxy and `contact_source="head_pose_proxy"` must be explicit.

### AI-avatar profile
WHY may be shared, WHEN is profile-specific:
- artifact peaks are hard candidates/windows;
- phoneme boundary alignment;
- forced cadence `2.0–4.0s` remains hard;
- silence trimming remains off where legacy profile requires it;
- artifact/accessory/hand integrity remains protected.

Mandatory anti-plastic drift is a profile renderer policy and must not be mistaken for semantic motion or used to extend STATIC_STRETCH.

---

## 11. Away behavior and contact

Remove hard rule `away >=1s => 1.00`.
Use `away/context_bias` and penalties/priors.

For v1.7.1 while only head-pose proxy exists, `continuous_contact` remains a hard prerequisite for entering `EMPHASIS` where legacy profile requires it. Document that this constraint may soften only after a true eye-gaze detector is introduced and calibrated.

Migrate all existing `at_camera` references to `head_facing_camera` / explicit contact proxy, including hard boundaries, emphasis admission, planned drift conditions, intimacy start and loop/poster gates.

---

## 12. Motion model

Separate artistic intent from render primitive.

### 12.1 Motion intent
- `static`
- `ambient_drift`
- `semantic_push`
- `semantic_pull`

### 12.2 Render primitive
- `hold`
- `step` / reframe
- `linear_ramp` (future easing may be versioned)

Both ambient drift and semantic push may compile to `linear_ramp` with different policy caps.

### 12.3 Discrete step
`delta_rel = abs(s2/s1 - 1)`.
Provisional minimum:
- calm `4%`
- neutral/high `6%`

Below threshold, do not create a discrete framing event.

### 12.4 Ambient drift
Legacy TR-13 intent:
- total push up to ~`×1.02` provisional;
- rate `<=0.5%/s` provisional.

Ambient drift intentionally does NOT extend static cap.

### 12.5 Semantic push
Relative only:
`target = min(start_scale * semantic_push_rel_cap, desired_scale, quality_cap, style_cap, window_geometry_cap)`

Initial provisional:
- `semantic_push_rel_cap = 1.06`;
- rate `<=1.5%/s`.

Geometry/headroom/caption checks must be computed at the worst/max target scale over the ramp.

---

## 13. STATIC_STRETCH and starvation

Remove ambiguous generic `motion_active` behavior.

Rules:
- discrete valid framing event resets static timer;
- ambient drift does not reset/extend static timer;
- semantic push may earn `motion_credit` / extend static cap by provisional `+3s` only when verified scale rate crosses the semantic-motion threshold;
- no-op events never reset timer;
- preserve the full existing starvation R1–R5 ladder and EDL reason codes;
- unify live fallback micro-drift maximum to `1.03` (remove conflicting `+0.04` behavior).

Pre-render verified scale rate comes from manifest derivative. Post-render scale rate is independently measured from rendered background scale tracking; optical flow is sanity evidence only.

---

## 14. HOME_RETURN, state balance, outro

HOME_RETURN:
- applies normally to unpatterned runs;
- for patterns, pattern metadata carries reset obligations;
- HOME_RETURN acts as safety net if pattern metadata is violated;
- provisional safety max `12s`.

State balance:
- rename old plan shares to state shares;
- calibration/info prior, not universal mechanical truth;
- provisional CONTEXT minimum: calm `.40`, neutral `.35`, high `.30`;
- ARGUMENT max `.45` provisional;
- remove hard `two plan3 in a row` rule; use emphasis share, history penalty and pattern state.

Outro breath provisional:
- calm `3.0s`, neutral `2.0s`, high `1.5s`;
- strong final emphasis (`semantic_weight >= .8` provisional) may reduce breath to minimum `1.0s` instead of forcing the full value.

---

## 15. Hook contract

Provisional `hook_cap=1.16`.
Cold open max duration `1.2s`.
Wide-boosted top is never used in hook.

Use feasible state names, not `step2`:
- intimacy start uses feasible `ARGUMENT` when available;
- cold open may use normal-style feasible `EMPHASIS` under hook cap;
- prop insert remains separately constrained.

---

## 16. Canonical framing schema

Timeline must contain the complete framing decision; renderer must not infer X/Y.

Example:
```json
{
  "framing": {
    "state": "EMPHASIS",
    "motion_intent": "semantic_push",
    "primitive": "linear_ramp",
    "crop_start": [54,81,964,1714],
    "crop_end": [71,96,938,1667],
    "anchor_policy": "tracked_face"
  }
}
```

`scale`, face ratio, margins and ramp deltas are derived diagnostics, not independent canonical truths. If stored, mark them derived.

Crop rules:
- X shift is limited by actual crop freedom as well as policy clamp;
- Y is clamped to `[0, H_in-H_crop]`;
- all dimensions are renderer-safe/even where required.

---

## 17. Determinism contract

Planner determinism is mandatory; source→semantic-analysis determinism is not.

For frozen analysis:
`analysis_hash + config_hash + planner_build/hash + schema_version => byte-stable canonical timeline`.

Requirements:
- canonical JSON serialization;
- fixed float rounding;
- zero randomness in planner;
- deterministic candidate ordering and tie-break;
- versioned weights/thresholds;
- stable IDs.

Suggested tie-break sequence: primary score descending, semantic fit descending, time ascending, stable ID lexicographic. Exact order must be encoded and unit-tested.

Regression tests use frozen `analysis.json` fixtures.

---

## 18. Timeline/EDL contract

Every framing decision must expose:
- WHY;
- DESIRED;
- CAN;
- WHEN;
- MOTION;
- `gates_passed`;
- `speech_impact`.

Example:
```text
WHY: contrast punchline, weight=.91
DESIRED: EMPHASIS
CAN: desired=1.18, quality=1.16, style=1.16, geometry(window)=1.12, actual=1.12
WHEN: word boundary + head-return bonus, breath-safe, blink/blur/prop-safe
MOTION: semantic_push compiled to linear_ramp
speech_impact: none
```

---

## 19. Critic / provenance / process integrity

Preserve PROCESS_INTEGRITY and CRITIC_PROVENANCE from the working baseline:
- critic report produced only by the critic executable;
- `script_sha256` / critic version;
- `master_sha256`;
- `inputs_sha256` / manifest hashes;
- independent two-pass behavior where Pass 1 inspects master without using timeline as truth;
- report provenance must be verifiable.

Mechanical critic registry resolves expected checks by profile/features.
Do not hardcode `35/40/...` in documentation or code.

Report three separate concepts:
- `coverage = reported_expected_ids / expected_ids`;
- `pass_rate = passed / applicable`;
- `verdict = NO_GO if any required check fails, else GO`.

Completeness means every expected ID appears with one of `pass|warn|fail|skip`; failures still count as reported.

Migration of legacy severity:
- PLAN_BALANCE → info/calibration;
- OUTRO_BREATH → warn/artistic prior;
- HOME_RETURN → NO_GO for unpatterned or violated pattern safety metadata;
- FACE_RATIO_P5/P95 → replaced by FEASIBLE_SHOT_STATES / composition checks; old IDs may be warn aliases during migration;
- STATIC_STRETCH remains NO_GO under the new motion-credit semantics.

New core mechanical checks:
- FEASIBLE_SHOT_STATES;
- COMPOSITION_SAFE;
- MOTION_FIDELITY / RAMP_FIDELITY;
- BREATH_GATE warn.

Do not put DRIFT_PERCEPTIBILITY in mechanical acceptance; perceptual adequacy belongs to director/calibration.

Post-render COMPOSITION_SAFE and framing fidelity must use independent measurement code, not planner geometry helpers.

---

## 20. Director review / retention

Retention remains informational.

Director review is:
- mandatory when artistic escalation trigger fires (e.g. retention below provisional threshold or critic requests artistic arbitration);
- optional otherwise.

The repo may provide a future skill/provider, but v1.7.1 core should depend on an interface, not assume a third skill directory already exists.

Add artistic axis `Semantic Synchrony`: whether framing/emphasis/reset motion follows the semantic curve.

---

## 21. KEEP list

Preserve unless explicitly migrated above:
- speech integrity / double transcription;
- silence trimming or 100% continuity profile behavior;
- 25ms cut fades;
- ambience handling;
- TR-17 music-bed detection;
- loudnorm chain;
- `rhythm_table` as single cadence source;
- blink/blur hard boundary protection;
- prop lifecycle TR-16;
- eye-closures TR-18;
- POSTER_FRAME/HF-8 behavior where present;
- `loop_state_match` / snap-back;
- overrides log and config auto-resolve;
- long-form act priors/calibration behavior;
- source normalization/stabilization;
- skill-2 contract;
- AI-avatar artifact protection and forced cadence;
- critic provenance/process integrity.

---

## 22. Errata / removals

Fix/document:
- HF-7 vs cold-open contract;
- calm ladder vs perceptibility via pace-aware relative threshold;
- schema note upgraded to v1.7.1;
- inconsistent wide-source examples/intensity-floor semantics;
- face target contradiction where a ~0.35 example passed a hard 0.38 lower bound;
- micro-drift 1.03 vs starvation +0.04 conflict;
- duplicated check-count constants replaced by registry.

Remove/deprecate:
- `Eye Return > Keyword > Pause > Rhythm` as global decision queue;
- hard theme→pattern map;
- hard away→1.00 rule;
- absolute semantic-hold target `<=1.06`;
- automatic wide-source style-cap bypass;
- `pattern_id != null => HOME_RETURN disabled`;
- `two plan3 in row forbidden`;
- fixed universal Plan3 lower face bound as planner/QC truth;
- new code using plan1/2/3 names.

---

## 23. Implementation order

### P0A — Contracts first
1. Freeze/reference baseline behavior and golden fixtures.
2. Add schema versions and canonical serialization.
3. Add analysis/config/timeline hashes and planner build ID.
4. Add deterministic tie-break tests.
5. Add critic registry/provenance contract scaffolding.

### P0B — Temporal geometry
1. Temporal composition measurements.
2. Feasibility intervals/map.
3. Quality/style cap separation.
4. Window-specific geometry cap.
5. Dynamic 1–3 feasible states.
6. Canonical X/Y crop framing.

### P0C — Planner
1. WHY intent.
2. PATTERN_SCORE with hard feasibility mask.
3. WHEN live/AI profile solvers.
4. Motion intent + primitive compilation.
5. EDL WHY/DESIRED/CAN/WHEN/MOTION.

### P0D — Validation
1. Planner invariants/pre-render validator.
2. Independent post-render framing/composition measurement.
3. Critic registry coverage/pass/verdict.
4. Provenance/process-integrity tests.

### P1+
Only after P0 is stable: TR-20/TR-21 semantics, richer composition aesthetics, semantic push calibration, director review integration, true gaze detector.

---

## 24. Regression suite

Minimum cases:
1. tight-face 1080p;
2. wide 1080p;
3. wide 4K boost off;
4. wide 4K boost on;
5. only 2 feasible states;
6. only 1 feasible state;
7. gesture creates temporal infeasibility mid-window;
8. strong away/head-turn + strong punchline;
9. semantic push;
10. ambient drift vs STATIC_STRETCH;
11. long semantic segment;
12. burned captions;
13. AI avatar artifact/forced cadence;
14. loop outro;
15. pattern degradation;
16. handheld + stabilization + zoom;
17. prop lifecycle transition windows;
18. premium-calm long segment with ambient drift that must NOT extend static cap;
19. deterministic tie scores;
20. critic registry with expected skip/warn/fail coverage.

---

## 25. Calibration

All new artistic numeric thresholds are `provisional=true` until calibrated.

Phase A smoke: >=10 diverse videos, paired old/new render on same raw.  
Phase B stabilization: >=30–50 diverse videos or sufficient real platform retention statistics.

Track:
- human preference;
- director score;
- semantic synchrony;
- mechanical rejection rate;
- platform retention when available.

Threshold promotion/demotion must be versioned and logged in overrides/calibration reports.

---

## 26. Definition of Done

v1.7.1 core is done when:
- deterministic planner executable exists;
- frozen same input/config/build produces byte-stable timeline;
- `analysis.json` contains observations, not planner policy decisions;
- temporal feasibility prevents circular geometry decisions;
- 1–3 feasible states are produced dynamically;
- plan1/2/3 terminology is absent from new runtime contracts;
- canonical timeline contains crop/anchor/motion framing, not scale-only intent;
- WHY is separated from WHEN;
- blink/blur/prop hard masks remain hard;
- live and AI-avatar WHEN paths are explicit;
- content hard cuts and framing decisions are formally separated;
- scale `<1.00` is impossible;
- wide boost is explicit opt-in;
- critic registry is dynamic and provenance/process-integrity is retained;
- post-render geometry verification is independent of planner geometry code;
- retention/drift perceptibility remain artistic/calibration signals, not mechanical hard gates;
- regression suite passes without ASR/sync/audio regressions.

## Architectural invariant

Every framing change must be explainable as:

`WHY → DESIRED → CAN(window) → WHEN → MOTION → CANONICAL FRAMING`

If the planner cannot fill those fields consistently, it must not create the framing change.
