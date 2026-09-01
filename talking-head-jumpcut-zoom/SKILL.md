# Talking-Head Jumpcut & Zoom Editor v1.7.6 Lite

## Minimal Semantic Episode Fix

This version is intentionally a **thin adapter over v1.7.5**, not a planner rewrite.

Read `SKILL_V1_7_5.md` as the base contract. Keep its cleanup, visual scan,
geometry, zoom states/caps, rendering, QC and pipeline guards unchanged unless
this file explicitly overrides a rule.

## Canonical v1.7.6 scripts

Use the normal v1.7.5 pipeline, but replace only these two calls:

```text
semantic_events.py -> semantic_events_v176.py
zoom_planner.py     -> zoom_planner_v176.py
```

The original v1.7.5 scripts remain unchanged and are imported as the core.
Do not add another orchestration layer.

## Scope: only three behavior changes

1. adjacent semantic marks may share `block_id`;
2. a semantic mark may specify `accent_word`;
3. zoom duration comes from the full semantic span and must not shrink because
   a later safe edit boundary was selected.

No new LLM pass, density controller, pause model, renderer or QC stage belongs
in v1.7.6.

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

`block_id` = one coherent thought/escalation. Reuse it only for genuinely
adjacent beats of the same thought.

`accent_word` must be inside `start_word..end_word`. The agent chooses the
word; deterministic code chooses milliseconds and the safe nearby boundary.

Legacy fallback remains valid:

```text
missing block_id    -> event id
missing accent_word -> start_word
```

## Episode rule

If adjacent planned non-context events share `block_id`, suppress the previous
auto-return when the next planned change follows it by at most 1200 ms.

Preferred:

```text
1.00 -> 1.08 -> 1.12 -> 1.00
```

Avoid:

```text
1.00 -> 1.08 -> 1.00 -> 1.12 -> 1.00
```

`release`, a new block, or a genuinely separated thought may still reset to
exact source/home framing.

## Accent timing

`semantic_events_v176.py` keeps the semantic span but centers boundary
candidates around `accent_word`.

`zoom_planner_v176.py` uses `accent_ms` as the target for WHEN.

Visual safety still wins. A blink, blur, unsafe pose, crop, face travel,
headroom or gesture/prop conflict can move or veto the transition.

## Duration invariant

```text
semantic_duration_ms = semantic_end_ms - semantic_start_ms
```

Duration classification uses that value, never:

```text
semantic_end_ms - selected_safe_boundary_ms
```

So WHEN may move without accidentally changing HOW LONG.

## Frequency

Keep the v1.7.5 rule:

```text
~1 visible semantic punch / 7 s = observational ceiling, not target
```

Never create a zoom to satisfy cadence.

For a 60-second talking-head clip, a normal result will often be roughly
4-8 visible zoom changes, sometimes fewer. The actual count follows semantic
marks, not a quota.

`zoom_planner_v176.py` writes `rhythm_summary`:

- `visible_zoom_change_count`
- `semantic_episode_count`
- `zoom_changes_per_min`
- `median_gap_between_zoom_changes_ms`
- observational ceiling `~8.57 changes/min`

This is diagnostic only in v1.7.6. It does not fail QC.

## Explicit non-goals

Do not change in v1.7.6:

- Family A/B/C pause cleanup;
- 1.00 / 1.08 / 1.12 / ratchet max 1.13;
- performance bonus;
- slow-push policy;
- geometry/headroom/Tripod Lock;
- cadence requests;
- pre/post render QC;
- pipeline guards.

If rendered tests expose another defect, fix that observed defect separately
instead of expanding this version pre-emptively.
