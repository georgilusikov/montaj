import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_events_v176 import build_events  # noqa: E402
from zoom_planner_v176 import plan  # noqa: E402


def dense_words(count=16, step=500):
    return [
        {"text": f"w{i}", "start_ms": i * step, "end_ms": i * step + 300}
        for i in range(count)
    ]


def observations(duration_ms=8000):
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
        }
        for t in range(0, duration_ms + 1, 200)
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
        result = plan({
            "source": {"width": 1080, "height": 1920, "duration_ms": 5000, "quality_cap": 1.25},
            "config": {"intensity": "moderate", "min_dwell_ms": 0},
            "observations": observations(5000),
            "semantic_events": [{
                "id": "e1",
                "t_ms": 1000,
                "accent_ms": 1000,
                "end_ms": 2600,
                "semantic_start_ms": 1000,
                "semantic_duration_ms": 1600,
                "block_id": "b1",
                "importance": 0.7,
                "boundary_candidates": [{"id": "late", "ms": 1400, "word_boundary": True, "ear": 0.30, "mar": 0.20}],
            }],
        })
        decision = next(d for d in result["decisions"] if d.get("status") == "PLANNED")
        self.assertEqual(decision["start_ms"], 1400)
        self.assertEqual(decision["zoom_duration_ms"], 1600)
        self.assertEqual(decision["end_ms"], 3000)

    def test_same_block_suppresses_intermediate_home_flash(self):
        result = plan({
            "source": {"width": 1080, "height": 1920, "duration_ms": 6000, "quality_cap": 1.25},
            "config": {"intensity": "moderate", "min_dwell_ms": 0},
            "observations": observations(6000),
            "semantic_events": [
                {
                    "id": "e1",
                    "t_ms": 1000,
                    "accent_ms": 1000,
                    "end_ms": 1800,
                    "semantic_start_ms": 1000,
                    "semantic_duration_ms": 800,
                    "block_id": "same",
                    "importance": 0.7,
                    "boundary_candidates": [{"id": "e1b", "ms": 1000, "word_boundary": True, "ear": 0.30, "mar": 0.20}],
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
                    "boundary_candidates": [{"id": "e2b", "ms": 2500, "word_boundary": True, "ear": 0.30, "mar": 0.20}],
                },
            ],
        })
        self.assertEqual(result["same_block_returns_suppressed"], 1)
        self.assertFalse(any(r.get("parent_event_id") == "e1" for r in result["returns"]))
        second = next(d for d in result["decisions"] if d.get("event_id") == "e2")
        self.assertEqual(second["motion"], "hold")
        self.assertEqual(second["crop_start"], second["crop_end"])
        self.assertIn("rhythm_summary", result)


if __name__ == "__main__":
    unittest.main()
