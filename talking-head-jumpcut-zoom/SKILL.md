# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

## Reels Cadence + Semantic Episode Fix

This version is intentionally a **thin adapter over v1.7.5**, not a planner rewrite.

Read `SKILL_V1_7_5.md` as the base contract. Keep its cleanup, visual scan,
geometry, rendering, QC and pipeline guards unchanged unless this file explicitly
overrides a rule.

## Canonical v1.7.6 scripts

Use the normal v1.7.5 pipeline, but replace only these two calls:

```text
semantic_events.py -> semantic_events_v176.py
zoom_planner.py     -> zoom_planner_v176.py
```

The original v1.7.5 semantic/planner scripts remain the deterministic core.
Do not add another orchestration layer.

## v1.7.6 behavior changes

1. adjacent semantic marks may share `block_id`;
2. a semantic mark may specify `accent_word`;
3. zoom duration comes from the full semantic span and does not shrink when a
   later safe boundary is selected;
4. Reels framing uses HOME / SOFT / PUNCH / PEAK / rare CLIMAX targets;
5. long visual gaps may create a cadence-only SOFT framing refresh.

No new LLM pass, pause model, renderer or planner stage belongs in v1.7.6.

## Semantic mark

Prefer:

```json
{
  "start_word": 10,
  "end_word": 16,
  "accent_word": 14,
  "block_id": "argument_02",
  "importance": 0.72,
  "why": "main contrast / thesis payoff"
}
```

`block_id` = one coherent thought/escalation. Reuse it only for adjacent beats
of the same thought.

`accent_word` must be inside `start_word..end_word`. The agent chooses the word;
deterministic code chooses milliseconds and a safe nearby boundary.

Legacy fallback remains valid:

```text
missing block_id    -> event id
missing accent_word -> start_word
```

## Reels framing grammar

Requested scales:

```text
HOME        1.00
SOFT        1.05
PUNCH       1.11
PEAK        1.14
CLIMAX_MAX  1.16
```

These are targets, not guaranteed crops. Existing geometry, quality, face
travel, gesture/prop safety and segment-wide headroom checks may reduce a
requested scale or veto it.

Roles:

```text
cadence refresh       -> SOFT only
semantic build        -> SOFT
normal semantic punch -> PUNCH
strong peak/payoff    -> PEAK
explicit ratchet_3    -> rare CLIMAX, max 1.16
```

Cadence must never create PUNCH, PEAK or CLIMAX.

## Reels cadence

Target visual rhythm:

```text
MIN_CHANGE_GAP       = 2.0 s
PREFERRED_CHANGE_GAP = 3.5 s
MAX_CHANGE_GAP       = 5.0 s
```

Interpretation:

- under ~2 s: normally do not change framing again;
- ~3–4 s: preferred Reels rhythm;
- after ~5 s without another visual change: try a SOFT refresh;
- semantic framing and real content jumpcuts reset the cadence clock;
- semantic framing always has priority over cadence.

Cadence is allowed to materialize only:

```text
HOME -> SOFT
SOFT -> HOME
```

If a semantic crop is active, cadence does not weaken it. If there is no safe
visual boundary/crop, HOLD is valid.

The result should often produce roughly 12–20 visible framing changes per
minute in a static talking-head Reels take, but this is a consequence of the
2–5 s cadence window, not a hard quota.

## Semantic episode continuity

If adjacent planned non-context events share `block_id`, suppress the previous
auto-return when the next planned change follows it closely.

Preferred progression:

```text
1.00 -> 1.05 -> 1.11 -> 1.14 -> 1.00
```

Avoid home-frame chatter:

```text
1.00 -> 1.05 -> 1.00 -> 1.11 -> 1.00 -> 1.14 -> 1.00
```

`release`, a new block, or a genuinely separated thought may reset to exact
HOME framing.

## Accent timing

`semantic_events_v176.py` keeps the full semantic span but centers boundary
candidates around `accent_word`.

`zoom_planner_v176.py` uses `accent_ms` as the target for WHEN.

Visual safety still wins. Blink, blur, unsafe pose, crop, face travel, headroom
or gesture/prop conflict can move or veto the transition.

## Duration invariant

```text
semantic_duration_ms = semantic_end_ms - semantic_start_ms
```

Duration classification uses that value, never:

```text
semantic_end_ms - selected_safe_boundary_ms
```

So WHEN may move without accidentally changing HOW LONG.

## Diagnostics

`zoom_planner_v176.py` writes `rhythm_summary` with:

- visible framing change count;
- semantic strong change count;
- cadence SOFT change count;
- semantic episode count;
- framing changes per minute;
- median gap between framing changes;
- configured 2.0 / 3.5 / 5.0 s cadence values.

This is diagnostic. Do not add another density controller in v1.7.6.

## QC

`simple_qc.py` remains backward-compatible with v1.7.5 and recognizes the
v1.7.6 Reels caps. It additionally fails if a cadence-created refresh exceeds
SOFT strength (`>~1.05`).

Unresolved cadence opportunities are warnings, not failures: safety/semantics
may legitimately force HOLD.

## Explicit non-goals

Do not add in v1.7.6:

- new LLM cadence planner;
- visual-energy accumulator;
- rolling density penalties;
- new pause model;
- filler deletion;
- new renderer;
- extra pipeline stage.

The intended architecture remains:

```text
v1.7.5 core
+ block/accent/duration adapter
+ small Reels scale/cadence adapter
= v1.7.6
```
