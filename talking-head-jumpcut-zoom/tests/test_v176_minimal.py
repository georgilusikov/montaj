import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_events_v176 import build_events  # noqa: E402
from simple_qc import check  # noqa: E402
from zoom_planner_v176 import ZOOM_LEVELS, _semantic_level, plan  # noqa: E402


def dense_words(count=30, step=500):
    return [
        {"text": f"w{i}", "start_ms": i * step, "end_ms": i * step + 300}
        for i in range(count)
    ]


def observations(duration_ms=16000):
    return [
        {
            "t_ms": t,
            "face_ratio": 0.22,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "eye_line_y": 0.29,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
            "ear": 0.30,
            "mar": 0.20,
            "laplacian_var": 120.0,
            "flow_speed_px": 0.4,
            "head_return": t % 1000 == 0,
        }
        for t in range(0, duration_ms + 1, 200)
    ]


def base_payload(duration_ms=9000, events=None):
    return {
        "source": {
            "width": 1080,
            "height": 1920,
            "duration_ms": duration_ms,
            "quality_cap": 1.20,
        },
        "config": {"intensity": "moderate", "min_dwell_ms": 0},
        "observations": observations(duration_ms),
        "semantic_events": list(events or []),
    }


def event(event_id, at_ms, importance, *, block_id="b", direction=None, duration_ms=1000, motion_hint=None):
    row = {
        "id": event_id,
        "t_ms": at_ms,
        "accent_ms": at_ms,
        "end_ms": at_ms + duration_ms,
        "semantic_start_ms": at_ms,
        "semantic_duration_ms": duration_ms,
        "block_id": block_id,
        "importance": importance,
        "semantic_importance": importance,
        "boundary_candidates": [{
            "id": f"{event_id}b",
            "ms": at_ms,
            "word_boundary": True,
            "ear": 0.30,
            "mar": 0.20,
        }],
    }
    if direction:
        row["direction"] = direction
    if motion_hint:
        row["motion_hint"] = motion_hint
    return row


def visible_decisions(result):
    return [
        d for d in result["decisions"]
        if d.get("status") == "PLANNED"
        and d.get("motion") != "hold"
        and d.get("crop_start") != d.get("crop_end")
    ]


class MinimalV176Tests(unittest.TestCase):
    def test_semantic_event_adds_block_accent_and_stable_duration(self):
        words = dense_words()
        result = build_events({
            "words": words,
            "semantic_marks": [{
                "id": "thesis",
                "start_word": 2,
                "end_word": 6,
                "accent_word": 5,
                "block_id": "argument_01",
                "importance": 0.8,
                "why": "main thesis",
            }],
        })
        built = result["semantic_events"][0]
        self.assertEqual(result["version"], "1.7.6-lite")
        self.assertEqual(built["block_id"], "argument_01")
        self.assertEqual(built["accent_word"], 5)
        self.assertEqual(built["accent_ms"], words[5]["start_ms"])
        self.assertEqual(built["semantic_duration_ms"], words[6]["end_ms"] - words[2]["start_ms"])

    def test_semantic_contract_requires_block_and_accent(self):
        words = dense_words()
        base = {
            "words": words,
            "semantic_marks": [{
                "id": "x",
                "start_word": 2,
                "end_word": 4,
                "importance": 0.7,
                "why": "important",
            }],
        }
        with self.assertRaisesRegex(ValueError, "block_id"):
            build_events(base)

        base["semantic_marks"][0]["block_id"] = "b"
        with self.assertRaisesRegex(ValueError, "accent_word"):
            build_events(base)

        legacy = {**base, "config": {"allow_legacy_semantic_defaults": True}}
        result = build_events(legacy)
        self.assertEqual(result["semantic_events"][0]["semantic_contract"], "legacy_fallback")

    def test_four_zoom_levels_are_bounded_at_113(self):
        self.assertEqual(ZOOM_LEVELS, {"Z1": 1.03, "Z2": 1.06, "Z3": 1.09, "Z4": 1.13})
        self.assertEqual(_semantic_level({"state": "ARGUMENT", "importance": 0.45, "semantic_importance": 0.45}), "Z1")
        self.assertEqual(_semantic_level({"state": "ARGUMENT", "importance": 0.60, "semantic_importance": 0.60}), "Z2")
        self.assertEqual(_semantic_level({"state": "ARGUMENT", "importance": 0.75, "semantic_importance": 0.75}), "Z3")
        self.assertEqual(_semantic_level({"state": "EMPHASIS", "importance": 0.95, "semantic_importance": 0.95}), "Z4")

    def test_performance_bonus_alone_cannot_create_z4(self):
        self.assertEqual(
            _semantic_level({"state": "EMPHASIS", "importance": 0.88, "semantic_importance": 0.80}),
            "Z3",
        )
        self.assertEqual(
            _semantic_level({"state": "EMPHASIS", "importance": 0.91, "semantic_importance": 0.91}),
            "Z4",
        )
        self.assertEqual(
            _semantic_level({"state": "ARGUMENT", "importance": 0.75, "semantic_importance": 0.75, "direction": "peak"}),
            "Z4",
        )

    def test_safe_boundary_does_not_change_semantic_duration_but_visual_dwell_is_two_seconds(self):
        result = plan(base_payload(6000, [{
            "id": "e1",
            "t_ms": 1000,
            "accent_ms": 1000,
            "end_ms": 2600,
            "semantic_start_ms": 1000,
            "semantic_duration_ms": 1600,
            "block_id": "b1",
            "importance": 0.7,
            "semantic_importance": 0.7,
            "boundary_candidates": [{
                "id": "late",
                "ms": 1400,
                "word_boundary": True,
                "ear": 0.30,
                "mar": 0.20,
            }],
        }]))
        decision = next(d for d in result["decisions"] if d.get("event_id") == "e1")
        self.assertEqual(decision["start_ms"], 1400)
        self.assertEqual(decision["semantic_duration_ms"], 1600)
        self.assertEqual(decision["zoom_duration_ms"], 2000)
        self.assertEqual(decision["end_ms"], 3400)

    def test_same_block_same_level_becomes_hold(self):
        result = plan(base_payload(8000, [
            event("e1", 1000, 0.65, block_id="same"),
            event("e2", 3200, 0.65, block_id="same"),
        ]))
        self.assertGreaterEqual(result["same_block_returns_suppressed"], 1)
        second = next(d for d in result["decisions"] if d.get("event_id") == "e2")
        self.assertEqual(second["zoom_level"], "Z2")
        self.assertEqual(second["motion"], "hold")
        self.assertEqual(second["crop_start"], second["crop_end"])

    def test_short_home_flash_between_blocks_is_suppressed(self):
        result = plan(base_payload(9000, [
            event("e1", 1000, 0.75, block_id="a", duration_ms=800),
            event("e2", 3500, 0.65, block_id="b", duration_ms=800),
        ]))
        self.assertGreaterEqual(result["short_home_flashes_suppressed"], 1)
        self.assertFalse([r for r in result["returns"] if r.get("parent_event_id") == "e1"])

    def test_cadence_starts_with_z1_and_never_exceeds_z2(self):
        result = plan(base_payload(12000))
        cadence = [d for d in visible_decisions(result) if d.get("cadence_refresh")]
        self.assertGreaterEqual(len(cadence), 2)
        levels = {d.get("zoom_level") for d in cadence}
        self.assertIn("Z1", levels)
        self.assertTrue(levels <= {"Z1", "Z2"})
        self.assertTrue(all(float(d.get("scale", 1.0)) <= 1.06 for d in cadence))

    def test_semantic_z3_at_four_seconds_suppresses_preceding_cadence(self):
        result = plan(base_payload(8000, [event("punch", 4000, 0.75, block_id="b1", duration_ms=1200)]))
        cadence_before = [
            d for d in result["decisions"]
            if d.get("cadence_refresh") and int(d.get("start_ms", 0)) < 4000
        ]
        self.assertFalse(cadence_before)
        punch = next(d for d in result["decisions"] if d.get("event_id") == "punch")
        self.assertEqual(punch["zoom_level"], "Z3")

    def test_same_block_can_progress_z2_to_z3_to_z4_without_home_flash(self):
        result = plan(base_payload(11000, [
            event("build", 1000, 0.65, block_id="arc", direction="build", duration_ms=1600),
            event("punch", 3400, 0.75, block_id="arc", duration_ms=1600),
            event("peak", 5800, 0.95, block_id="arc", direction="peak", duration_ms=1600),
        ]))
        build = next(d for d in result["decisions"] if d.get("event_id") == "build")
        punch = next(d for d in result["decisions"] if d.get("event_id") == "punch")
        peak = next(d for d in result["decisions"] if d.get("event_id") == "peak")

        self.assertEqual(build["zoom_level"], "Z2")
        self.assertEqual(punch["zoom_level"], "Z3")
        self.assertEqual(peak["zoom_level"], "Z4")
        self.assertGreater(punch["scale"], build["scale"])
        self.assertGreater(peak["scale"], punch["scale"])
        self.assertLessEqual(peak["scale"], 1.13)
        self.assertFalse(any(r.get("parent_event_id") in {"build", "punch"} for r in result["returns"]))

    def test_slow_push_has_settle_or_falls_back_to_step(self):
        result = plan(base_payload(8000, [
            event("push", 1000, 0.75, block_id="b", direction="build", duration_ms=1600, motion_hint="slow_push"),
        ]))
        push = next(d for d in result["decisions"] if d.get("event_id") == "push")
        if push["motion"] == "slow_push":
            self.assertGreaterEqual(push["end_ms"] - push["transition_end_ms"], 300)
        else:
            self.assertEqual(push["motion"], "step")

    def test_qc_enforces_global_two_second_framing_gap(self):
        result = plan(base_payload(12000))
        report = check(result)
        self.assertEqual(report["status"], "PASS")

        bad = {
            "version": "1.7.6-lite",
            "source": {"width": 1080, "height": 1920, "duration_ms": 5000},
            "config": {"semantic_contract_required": False},
            "decisions": [
                {
                    "event_id": "a", "status": "PLANNED", "start_ms": 1000, "end_ms": 3000,
                    "motion": "step", "state": "SOFT", "zoom_level": "Z1", "scale": 1.03,
                    "crop_start": [0, 0, 1080, 1920], "crop_end": [16, 28, 1048, 1864],
                },
                {
                    "event_id": "b", "status": "PLANNED", "start_ms": 1800, "end_ms": 3800,
                    "motion": "step", "state": "SOFT", "zoom_level": "Z2", "scale": 1.06,
                    "crop_start": [16, 28, 1048, 1864], "crop_end": [30, 54, 1018, 1812],
                },
            ],
            "returns": [],
        }
        bad_report = check(bad)
        self.assertEqual(bad_report["status"], "FAIL")
        self.assertIn("framing_change_too_fast", {e["check"] for e in bad_report["errors"]})

    def test_rhythm_summary_reports_level_counts_and_min_gap(self):
        result = plan(base_payload(12000))
        summary = result["rhythm_summary"]
        self.assertEqual(set(summary["zoom_level_counts"]), {"Z1", "Z2", "Z3", "Z4"})
        self.assertGreaterEqual(summary["zoom_level_counts"]["Z1"], 1)
        self.assertGreaterEqual(summary["minimum_gap_between_framing_changes_ms"], 2000)


if __name__ == "__main__":
    unittest.main()
