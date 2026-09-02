# v1.7.6 A/B: Energy Director vs Research-Aligned Director

Compare the same dense source, transcript, semantic marks, subtitles and export settings.

## A — `skill/v1.7.6-semantic-episode`

- mandatory safe opening motion around ~0.8 s and ~3.9 s when semantics do not replace it;
- generated editorial-energy checkpoints around ~4.5 s in sparse areas;
- profile max 1.12;
- ~3 s anti-chatter floor;
- slow-push settle >=0.5 s.

## B — `skill/v1.7.6-research-aligned`

- opening motion is optional; HOME is valid without semantic WHY;
- cadence produces `refresh_requests` only and never synthetic zoom events;
- semantic importance/role chooses target framing;
- editorial-energy slope chooses motion style only;
- gradual rise may SLOW_PUSH, sharp rise/peak stays STEP;
- hard visible-change floor ~1.2 s, preferred semantic dwell ~2.4 s;
- preferred slow-push settle ~0.9 s, hard minimum 0.5 s;
- Z4 / artistic hard cap 1.13;
- same geometry, >=5% headroom, face/gesture/caption safety, renderer and QC family.

## Compare

For each identical clip record:

- owner blind preference A/B;
- visible framing changes per minute;
- semantic vs synthetic changes;
- median/min gap between visible changes;
- Z1/Z2/Z3/Z4 counts;
- slow-push count and settle duration;
- visible HOME flashes / ping-pong;
- safety/QC failures;
- later, if published: 2 s / 5 s retention, 25% / 50% retention and completion rate.

Do not change content cuts or semantic marks between variants if the goal is to isolate directing policy.
