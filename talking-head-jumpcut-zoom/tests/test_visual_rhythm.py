import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zoom_planner import plan  # noqa: E402
from render_zoom import _commands  # noqa: E402
from simple_qc import check  # noqa: E402


def observations(duration_ms=12000, face_ratio=0.20):
    return [
        {
            "t_ms": t,
            "face_ratio": face_ratio,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
        }
        for t in range(0, duration_ms + 1, 250)
    ]


def event(event_id, t_ms, end_ms, *, direction="build", importance=0.70):
    return {
        "id": event_id,
        "t_ms": t_ms,
        "end_ms": end_ms,
        "importance": importance,
        "direction": direction,
        "boundary_candidates": [{"id": f"b-{event_id}", "ms": t_ms, "word_boundary": True}],
    }


def payload(events, duration_ms=12000):
    return {
        "source": {"width": 2160, "height": 3840, "quality_cap": 1.60, "duration_ms": duration_ms},
        "config": {"intensity": "moderate", "window_ms": 600},
        "observations": observations(duration_ms),
        "semantic_events": events,
    }


class VisualRhythmTests(unittest.TestCase):
    def test_build_uses_slow_soft_105_push(self):
        result = plan(payload([event("build", 1000, 4000, direction="build", importance=0.80)], duration_ms=5000))
        decision = result["decisions"][0]
        self.assertEqual(decision["state"], "ARGUMENT")
        self.assertTrue(decision["soft_build"])
        self.assertEqual(decision["motion"], "slow_push")
        self.assertAlmostEqual(decision["scale"], 1.05, places=3)
        self.assertEqual(decision["transition_end_ms"] - decision["start_ms"], 2400)

    def test_peak_remains_fast_semantic_step(self):
        result = plan(payload([event("peak", 1000, 2200, direction="peak", importance=0.95)], duration_ms=4000))
        decision = result["decisions"][0]
        self.assertEqual(decision["state"], "EMPHASIS")
        self.assertFalse(decision["soft_build"])
        self.assertEqual(decision["motion"], "step")
        self.assertGreaterEqual(decision["scale"], 1.12)
        self.assertEqual(decision["transition_end_ms"], decision["start_ms"])

    def test_long_neutral_gap_gets_closed_nonsemantic_refresh_cycle(self):
        result = plan(payload([], duration_ms=12000))
        self.assertGreaterEqual(len(result["refreshes"]), 2)
        push, pull = result["refreshes"][:2]
        self.assertEqual(push["ambient_phase"], "push")
        self.assertEqual(pull["ambient_phase"], "pull")
        self.assertFalse(push["semantic_trigger"])
        self.assertFalse(pull["semantic_trigger"])
        self.assertEqual(push["motion"], "slow_push")
        self.assertEqual(pull["motion"], "slow_push")
        self.assertLessEqual(push["scale"], 1.04)
        self.assertEqual(pull["crop_end"], [0, 0, 2160, 3840])
        self.assertLessEqual(push["start_ms"], 5000)
        self.assertEqual(check(result)["status"], "PASS")

    def test_short_neutral_gap_does_not_manufacture_refresh(self):
        result = plan(payload([], duration_ms=4500))
        self.assertEqual(result["refreshes"], [])

    def test_renderer_contains_ambient_interpolation_commands(self):
        result = plan(payload([], duration_ms=12000))
        commands = _commands(result)
        first = result["refreshes"][0]
        self.assertIn(f"{first['start_ms'] / 1000.0:.6f} crop@thz", commands)
        self.assertIn(f"{first['transition_end_ms'] / 1000.0:.6f} crop@thz", commands)


if __name__ == "__main__":
    unittest.main()
