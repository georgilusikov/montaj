---
name: talking-head-jumpcut-zoom
description: 'A/B research-aligned talking-head Reels/Shorts/TikTok editor: conservative pause cleanup, semantic target framing, editorial-energy motion, optional opening movement, cadence refresh requests only, four restrained zoom levels, guarded render and visual/pixel QC.'
---

# Talking-Head Jumpcut & Zoom Editor v1.7.6 Research-Aligned

## A/B purpose

This branch is the B-variant for comparison with `skill/v1.7.6-semantic-episode`.
It deliberately changes **directing policy only**. Geometry, headroom, boundary safety,
renderer, speech cleanup and QC stay inherited from the same v1.7.6 core.

Core rule:

```text
SEMANTICS -> target framing
EDITORIAL ENERGY SLOPE -> motion style
CADENCE -> diagnostic refresh request only
SAFETY -> may reduce or veto every crop
```

`editorial_energy` is not claimed to be measured viewer attention or retention.

## Canonical entry points

```text
speech_cleanup.py
semantic_events_v176.py
zoom_planner_energy_v176.py   <- B-variant director
```

Do not add another LLM pass, renderer, density controller or timeline framework.

## Pause cleanup

Unchanged from the current v1.7.6 Reels adapter.

Family A preserves timing by default.

Family B:

```text
cut_threshold_ms = 450
target_gap_ms     = 450
```

Pauses `<=450 ms` remain intact; longer pauses are shortened to about `450 ms`.
Spoken words are never removed by strict cleanup.

## Semantic contract

For every important non-release semantic mark (`raw importance >=0.40`):

```text
WHY + block_id + accent_word
```

The agent owns WHY and semantic importance. Deterministic code owns the exact safe
boundary and crop.

`accent_word` is a semantic anchor, not an instruction to cut on one exact frame.
A safe boundary near the beginning of the accent span may be better than waiting until
the accented word itself if that gives the visual change time to register.

## Camera levels

The B profile keeps restrained low levels but restores the user-selected artistic max:

```text
HOME = 1.00
Z1   = 1.03
Z2   = 1.05
Z3   = 1.08
Z4   = 1.13

ABS HARD CAP = 1.13
```

Exact numeric levels are an A/B calibration choice, not a claimed scientific optimum.
Geometry may always reduce them.

Z4 remains semantic-only: real strong semantic importance / peak / ratchet climax is
required. Cadence or editorial-energy diagnostics may never manufacture Z4.

## Editorial energy: motion only

For each **real semantic event**, derive a lightweight `editorial_energy` value from
existing importance, direction and bounded performance evidence.

Do not overwrite semantic importance with energy.

Therefore:

```text
semantic importance / role -> HOME / Z1 / Z2 / Z3 / Z4
energy slope              -> HOW to reach that target
```

Default motion mapping:

```text
gradual rise -> SLOW_PUSH
sharp rise   -> STEP
flat         -> HOLD when target already matches; otherwise STEP
fall         -> STEP to the semantic target / explicit semantic release
peak/payoff  -> STEP
```

Energy by itself does not invent a release or a stronger semantic target.

## Opening: no mandatory synthetic movement

There is **no required 0.8 s / 3.9 s opening ramp** in this B variant.

```text
real semantic hook -> frame it normally
no semantic hook    -> HOME is allowed
```

An opening may still move when a real semantic `build` or other real semantic event
justifies it. The absence of camera motion in the first five seconds is not itself an
error.

No synthetic intro semantic events are generated.

## Cadence: guard rail only

Timing is not WHY.

Use the old Reels rhythm only as a static-gap diagnostic:

```text
~4.5 s  useful checkpoint, not an event
>6.0 s  emit a refresh_request if the frame stayed static
```

A `refresh_request` does **not** materialize a zoom.
Preferred resolution order outside this zoom planner:

```text
1. real content jumpcut already available
2. caption / graphic visual change
3. upcoming semantic framing change
4. optional weak Z1 only if an editor explicitly chooses it
5. HOLD is valid
```

This B branch never converts the timer into synthetic editorial-energy points.

## Anti-chatter timing

The old `3.0 s` rule is no longer a hard semantic-change floor.

```text
hard visible-change floor ~= 1.2 s
preferred semantic dwell  ~= 2.4 s
```

Meaning may justify a real stronger event before three seconds. The hard floor only
prevents pathological chatter.

Same-block continuity remains authoritative:

```text
same block + same level -> HOLD
same block + stronger semantic target -> progress directly upward
short HOME flash before the next event -> suppress
explicit release / new semantic block -> HOME when appropriate
```

## Slow push and readable settle

Slow push remains selective, not constant camera drift.

```text
target transition       ~= 2.0 s
preferred stable settle ~= 0.9 s
hard minimum settle     = 0.5 s
minimum useful push     ~= 1.2 s
```

If an episode cannot fit a useful push plus at least the hard settle, fall back to STEP.
When there is enough room, prefer about `0.8–1.2 s` of stable framing after the push.

## Safety and composition

Unchanged from the shared v1.7.6 core:

- Tripod Lock / no per-frame face chasing;
- global optical and eye-line anchor;
- face-travel checks over the whole framing episode;
- gesture/prop/caption safety;
- segment-wide headroom;
- `>=5%` air above hair when evidence exists;
- blink/blur/pose/motion rejection;
- quality and crop bounds;
- artistic hard cap `1.13`.

Safety may reduce a requested scale to any smaller safe framing or veto it entirely.

## Diagnostics for the A/B test

The B plan exposes:

```text
editorial_energy_curve       semantic points only
generated_energy_events      always 0
intro_energy_events_added    always 0
energy_checkpoints_added     always 0
refresh_requests             cadence diagnostics only
rhythm_summary
```

Important config receipts:

```text
editorial_energy_role       = motion_only
semantic_role               = target_framing
mandatory_opening_motion    = false
cadence_materializes_zoom   = false
hard_change_floor_ms        = 1200
preferred_semantic_dwell_ms = 2400
slow_push_preferred_settle_ms = 900
absolute_zoom_cap           = 1.13
```

## A/B interpretation

Compare the same dense source and the same semantic marks between:

```text
A = skill/v1.7.6-semantic-episode
    synthetic opening ramp + generated energy checkpoints

B = skill/v1.7.6-research-aligned
    semantic-only framing + energy-slope motion + refresh requests only
```

Do not change subtitles, source take, transcript, semantic marks or export settings
between A and B. Otherwise the comparison stops isolating directing policy.

Useful measurements:

- visible framing changes per minute;
- median/minimum gap between changes;
- number of synthetic vs semantic changes;
- Z1/Z2/Z3/Z4 counts;
- slow-push count and settle duration;
- owner preference on the same clips;
- later: actual platform retention curves if available.

## Definition of done

- No synthetic opening camera requirement.
- No synthetic editorial-energy checkpoints.
- Cadence creates requests, never zoom decisions.
- Semantic importance chooses framing level.
- Energy slope chooses motion style only.
- Sharp peaks remain STEP.
- Gradual rises may slow-push.
- Real semantic changes can occur after ~1.2 s instead of waiting for 3 s.
- Slow pushes prefer ~0.9 s readable settle.
- Z4 / global artistic cap is 1.13.
- Existing headroom, geometry, safety, guarded render and QC remain intact.
