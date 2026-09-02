# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

## Reels Four-Level Cadence

This remains a **thin adapter over v1.7.5**, not a planner rewrite.

Use the normal v1.7.5 pipeline, replacing only:

```text
semantic_events.py -> semantic_events_v176.py
zoom_planner.py     -> zoom_planner_v176.py
```

No new LLM pass, pause model, renderer, density controller or pipeline stage.

## Core idea

```text
CADENCE   -> lower zoom levels only
SEMANTICS -> any level, including strong levels
```

Cadence keeps a Reels frame alive. Semantics controls strong emphasis.

## Framing grammar

Exact source/home frame:

```text
HOME = 1.00
```

Four zoom levels:

```text
Z1 = 1.03   subtle refresh
Z2 = 1.06   clear but light push
Z3 = 1.09   semantic punch
Z4 = 1.13   strong peak / payoff
```

`1.13` is the hard artistic maximum.

The steps are intentionally not required to be perfectly equal. Existing geometry,
quality, face travel, gesture/prop safety and segment-wide headroom checks may reduce a
requested scale. Safe fallbacks may therefore land slightly below the nominal target.

## Semantic level selection

Default mapping after the existing bounded performance bonus:

```text
importance 0.40–0.54 -> Z1
importance 0.55–0.71 -> Z2
importance 0.72–0.84 -> Z3
importance >= 0.85   -> Z4
```

Direction overrides:

```text
build / ratchet_1 -> Z2
ratchet_2         -> Z3
peak / EMPHASIS   -> Z4
ratchet_3         -> Z4
release           -> HOME
```

Thus an ordinary important point can use Z2/Z3 while Z4 remains reserved for a real
peak/payoff. Cadence alone can never create Z3 or Z4.

## Cadence frequency

Keep the existing Reels timing window:

```text
MIN_CHANGE_GAP       = 2.0 s
PREFERRED_CHANGE_GAP = 3.5 s
MAX_CHANGE_GAP       = 5.0 s
```

Interpretation:

- under ~2 s: normally do not change framing again;
- around 3–4 s: preferred refresh timing;
- after ~5 s without a real visual change: try a cadence refresh;
- semantic framing and content jumpcuts reset the cadence clock;
- semantic framing always has priority;
- if no safe crop/boundary exists, HOLD is valid.

Cadence may use only the lower two levels:

```text
HOME -> Z1 -> Z2 -> Z1 ...
```

It never escalates itself to Z3/Z4.

Do **not** hard-code a quota such as “three Z4 shots per minute”. Upper-level frequency
must follow semantic density. For a typical ~60 s Reels take, the expected shape is:

```text
overall framing changes: roughly every 2–5 s
Z1/Z2: most changes
Z3: several semantic punches when justified
Z4: a few genuine peaks, possibly only one
```

These are expectations, not quotas.

## Semantic episode continuity

Adjacent events sharing `block_id` should progress without flashing HOME between beats.

Preferred:

```text
1.00 -> Z1/Z2 -> Z3 -> Z4 -> 1.00
```

Avoid:

```text
1.00 -> zoom -> 1.00 -> zoom -> 1.00 -> zoom
```

`release`, a new block, or a genuinely separated thought may reset HOME.

## Accent timing

`accent_word` selects the semantic target. Deterministic code maps it to `accent_ms`
and chooses a nearby safe visual/word boundary.

Visual safety can move or veto the change.

## Duration invariant

```text
semantic_duration_ms = semantic_end_ms - semantic_start_ms
```

A shifted safe boundary may change WHEN but not HOW LONG.

## Diagnostics

`rhythm_summary` reports:

- total visible framing changes;
- semantic vs cadence changes;
- semantic episodes;
- `Z1/Z2/Z3/Z4` counts;
- framing changes per minute;
- median gap;
- configured 2.0 / 3.5 / 5.0 s cadence window.

Use these numbers to calibrate real gold Reels later. Do not add a new frequency
controller until real videos show a repeatable problem.

## QC

v1.7.6 QC enforces:

```text
hard cap = 1.13
cadence max = Z2 / 1.06
Z1 <= 1.03
Z2 <= 1.06
Z3 <= 1.09
Z4 <= 1.13
```

Unresolved cadence opportunities remain warnings, not failures.

## Architecture

```text
v1.7.5 core
+ block/accent/duration adapter
+ four-level Reels cadence adapter
= v1.7.6
```
