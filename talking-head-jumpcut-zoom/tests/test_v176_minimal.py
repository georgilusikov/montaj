import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_events_v176 import build_events  # noqa: E402
from simple_qc import check  # noqa: E402
from zoom_planner_v176 import plan  # noqa: E402


def dense_words(count=20, step=500):
    return [
        {"text": f"w{i}", "start_ms": i * step, "end_ms": i * step + 300}
        for i in range(count)
    ]


def observations(duration_ms=10000):
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


def base_payload(duration_ms=7000, events=None):
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
        event = result["semantic_events"][0]
        self.assertEqual(result["version"], "1.7.6-lite")
        self.assertEqual(event["block_id"], "argument_01")
        self.assertEqual(event["accent_word"], 5)
        self.assertEqual(event["accent_ms"], words[5]["start_ms"])
        self.assertEqual(event["semantic_duration_ms"], words[6]["end_ms"] - words[2]["start_ms"])
        nearest = min(event["boundary_candidates"], key=lambda c: abs(c["ms"] - event["accent_ms"]))
        self.assertLessEqual(abs(nearest["ms"] - event["accent_ms"]), 300)

    def test_zoom_duration_does_not_shrink_when_safe_boundary_is_late(self):
        result = plan(base_payload(5000, [{
            "id": "e1",
            "t_ms": 1000,
            "accent_ms": 1000,
            "end_ms": 2600,
            "semantic_start_ms": 1000,
            "semantic_duration_ms": 1600,
            "block_id": "b1",
            "importance": 0.7,
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
        self.assertEqual(decision["zoom_duration_ms"], 1600)
        self.assertEqual(decision["end_ms"], 3000)

    def test_same_block_suppresses_intermediate_home_flash(self):
        result = plan(base_payload(6000, [
            {
                "id": "e1",
                "t_ms": 1000,
                "accent_ms": 1000,
                "end_ms": 1800,
                "semantic_start_ms": 1000,
                "semantic_duration_ms": 800,
                "block_id": "same",
                "importance": 0.7,
                "boundary_candidates": [{
                    "id": "e1b",
                    "ms": 1000,
                    "word_boundary": True,
                    "ear": 0.30,
                    "mar": 0.20,
                }],
            },
            {
                "id": "e2",
                "t_ms": 2500,
                "accent_ms": 2500,
                "end_ms": 3300,
                "semantic_start_ms": 2500,
                "semantic_duration_ms": 800,
                "block_id": "same",
                "importance": 0.7,
                "boundary_candidates": [{
                    "id": "e2b",
                    "ms": 2500,
                    "word_boundary": True,
                    "ear": 0.30,
                    "mar": 0.20,
                }],
            },
        ]))
        self.assertEqual(result["same_block_returns_suppressed"], 1)
        self.assertFalse(any(r.get("parent_event_id") == "e1" for r in result["returns"]))
        second = next(d for d in result["decisions"] if d.get("event_id") == "e2")
        self.assertEqual(second["motion"], "hold")
        self.assertEqual(second["crop_start"], second["crop_end"])
        self.assertIn("rhythm_summary", result)

    def test_cadence_creates_only_soft_refresh_in_long_semantic_gap(self):
        result = plan(base_payload(7000))
        cadence = [d for d in visible_decisions(result) if d.get("cadence_refresh")]
        self.assertTrue(cadence)
        first = cadence[0]
        self.assertEqual(first["reels_role"], "SOFT_REFRESH")
        self.assertGreaterEqual(first["start_ms"], 2000)
        self.assertLessEqual(first["start_ms"], 5000)
        self.assertLessEqual(first["scale"], 1.05)
        self.assertGreater(first["scale"], 1.0)

    def test_semantic_punch_at_four_seconds_suppresses_preceding_soft_refresh(self):
        event = {
            "id": "punch",
            "t_ms": 4000,
            "accent_ms": 4000,
            "end_ms": 5200,
            "semantic_start_ms": 4000,
            "semantic_duration_ms": 1200,
            "block_id": "b1",
            "importance": 0.75,
            "boundary_candidates": [{
                "id": "pb",
                "ms": 4000,
                "word_boundary": True,
                "ear": 0.30,
                "mar": 0.20,
            }],
        }
        result = plan(base_payload(7000, [event]))
        cadence_before = [
            d for d in result["decisions"]
            if d.get("cadence_refresh") and int(d.get("start_ms", 0)) < 4000
        ]
        self.assertFalse(cadence_before)
        punch = next(d for d in result["decisions"] if d.get("event_id") == "punch")
        self.assertEqual(punch["reels_role"], "PUNCH")
        self.assertGreaterEqual(punch["scale"], 1.08)
        self.assertLessEqual(punch["scale"], 1.115)

    def test_cadence_never_creates_punch_or_peak(self):
        result = plan(base_payload(12000))
        cadence = [d for d in visible_decisions(result) if d.get("cadence_refresh")]
        self.assertGreaterEqual(len(cadence), 2)
        self.assertTrue(all(float(d.get("scale", 1.0)) <= 1.05 for d in cadence))
        self.assertTrue(all(d.get("reels_role") in {"SOFT_REFRESH", "SOFT_RETURN"} for d in cadence))
        report = check(result)
        self.assertEqual(report["status"], "PASS")

    def test_same_block_can_progress_soft_to_punch_to_peak_without_home_flash(self):
        events = [
            {
                "id": "build",
                "t_ms": 1000,
                "accent_ms": 1000,
                "end_ms": 2600,
                "semantic_start_ms": 1000,
                "semantic_duration_ms": 1600,
                "block_id": "arc",
                "importance": 0.65,
                "direction": "build",
                "motion_hint": "step",
                "boundary_candidates": [{
                    "id": "b1", "ms": 1000, "word_boundary": True, "ear": 0.30, "mar": 0.20
                }],
            },
            {
                "id": "punch",
                "t_ms": 3000,
                "accent_ms": 3000,
                "end_ms": 4600,
                "semantic_start_ms": 3000,
                "semantic_duration_ms": 1600,
                "block_id": "arc",
                "importance": 0.75,
                "boundary_candidates": [{
                    "id": "b2", "ms": 3000, "word_boundary": True, "ear": 0.30, "mar": 0.20
                }],
            },
            {
                "id": "peak",
                "t_ms": 5000,
                "accent_ms": 5000,
                "end_ms": 6600,
                "semantic_start_ms": 5000,
                "semantic_duration_ms": 1600,
                "block_id": "arc",
                "importance": 0.95,
                "direction": "peak",
                "boundary_candidates": [{
                    "id": "b3", "ms": 5000, "word_boundary": True, "ear": 0.30, "mar": 0.20
                }],
            },
        ]
        result = plan(base_payload(8000, events))
        build = next(d for d in result["decisions"] if d.get("event_id") == "build")
        punch = next(d for d in result["decisions"] if d.get("event_id") == "punch")
        peak = next(d for d in result["decisions"] if d.get("event_id") == "peak")

        self.assertEqual(build["reels_role"], "SOFT")
        self.assertLessEqual(build["scale"], 1.05)
        self.assertEqual(punch["reels_role"], "PUNCH")
        self.assertGreater(punch["scale"], build["scale"])
        self.assertEqual(peak["reels_role"], "PEAK")
        self.assertGreater(peak["scale"], punch["scale"])

        self.assertFalse(any(
            r.get("parent_event_id") in {"build", "punch"}
            for r in result["returns"]
        ))
        self.assertNotEqual(punch["crop_start"], [0, 0, 1080, 1920])
        self.assertNotEqual(peak["crop_start"], [0, 0, 1080, 1920])


if __name__ == "__main__":
    unittest.main()
