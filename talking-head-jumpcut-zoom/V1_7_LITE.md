# Talking-Head Jumpcut & Zoom Editor v1.7.6 Energy

`SKILL.md` is the canonical production instruction. This file is the compact engineering contract.

## Architecture

```text
normalize -> Whisper -> speech_cleanup -> visual_scan
-> semantic_events_v176
-> zoom_planner_energy_v176
   -> zoom_planner_v176 core
-> QC/review -> render -> pixel/final QC
```

The energy layer is deterministic and adds no LLM pass or renderer stage.

## Pause policy

Family B preserves pauses through `450 ms`; longer pauses are reduced to about `450 ms`.
Family A remains conservative.

## Camera grammar

```text
HOME 1.00
Z1   1.03
Z2   1.05
Z3   1.08
Z4   1.12
PROFILE CAP 1.12
```

Generated editorial-energy events may use only Z1-Z3. Z4 remains semantic-only.

## Editorial energy

Each real semantic event gets `editorial_energy` in `0..1` from existing effective importance, semantic direction and bounded performance salience.
The value is an editorial-control signal, not measured viewer attention.

```text
rise_fast -> STEP upward
rise      -> SLOW_PUSH upward
hold      -> keep framing when suitable
fall      -> lower zoom level
fall_fast / low energy -> release HOME
```

Energy between real semantic events is interpolated. If the clip has no upcoming semantic event, energy slowly decays toward a calmer framing.

## First 5 seconds

Opening cannot remain visually static when a safe crop exists.
The director targets a low-level rising ramp around:

```text
~0.8 s -> Z1 1.03
~3.9 s -> Z2 1.05
```

Nearby real semantic events replace synthetic intro events.
Intro movement prefers eased slow push.

## Timing guard rail

```text
normal minimum gap: ~3.0 s
preferred checkpoint: ~4.5 s
fallback refresh after: ~6.0 s
```

This is not the cause of a semantic zoom. Energy/meaning chooses the camera trajectory; cadence only prevents unusually long visual stasis.

After the opening, generated energy checkpoints are considered roughly every `4.5 s` when no real semantic event is nearby.

## Motion

```text
slow push target ~2.0 s
settle >=0.5 s
```

Sharp peaks stay STEP. Gradual rises may slow-push.

## Semantic contract

Important non-release marks still require:

```text
WHY + block_id + accent_word
```

Raw semantic importance is preserved separately so performance/generated energy cannot manufacture Z4.

## Safety

Inherited v1.7.5/v1.7.6 safety remains authoritative: Tripod Lock, optical/eye-line anchor, face travel, gesture/prop/caption protection, segment-wide headroom, blink/blur/pose/motion rejection and quality/crop bounds.

## Diagnostics

```text
editorial_energy_curve
intro_energy_events_added
energy_checkpoints_added
intro_energy_movement
rhythm_summary
```

## Provenance

Production guard remains compatible because the energy zoom plan reports `1.7.6-energy` and semantic artifacts remain `1.7.6*`.
