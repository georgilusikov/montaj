import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zoom_planner import plan  # noqa: E402
from render_zoom import _commands  # noqa: E402


def observations(face_ratio=0.20):
    return [
        {
            "t_ms": t,
            "face_ratio": face_ratio,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
        }
        for t in range(0, 10000, 250)
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


def payload(events):
    return {
        "source": {"width": 2160, "height": 3840, "quality_cap": 1.60},
        "config": {"intensity": "moderate", "window_ms": 600},
        "observations": observations(),
        "semantic_events": events,
    }


class ZoomDurationTests(unittest.TestCase):
    def test_short_clause_becomes_micro_punch_and_returns(self):
        result = plan(payload([event("micro", 1000, 2100)]))
        decision = result["decisions"][0]
        self.assertEqual(decision["zoom_duration_type"], "micro_punch")
        self.assertEqual(decision["zoom_duration_ms"], 1100)
        self.assertTrue(decision["auto_return"])
        self.assertEqual(len(result["returns"]), 1)
        self.assertEqual(result["returns"][0]["start_ms"], 2100)
        self.assertEqual(result["returns"][0]["why"], "auto_return_context")

    def test_long_clause_is_clamped_to_argument_hold_band(self):
        result = plan(payload([event("long", 1000, 7000)]))
        decision = result["decisions"][0]
        self.assertEqual(decision["zoom_duration_type"], "argument_hold")
        self.assertEqual(decision["zoom_duration_ms"], 3500)
        self.assertEqual(result["returns"][0]["start_ms"], 4500)

    def test_nearby_peak_extends_tension_instead_of_flashing_context(self):
        data = payload(
            [
                event("build", 1000, 1900, direction="build", importance=0.80),
                event("peak", 2200, 3000, direction="peak", importance=0.95),
            ]
        )
        result = plan(data)
        first, second = result["decisions"]
        self.assertTrue(first["continued_by_next"])
        self.assertFalse(first["auto_return"])
        self.assertEqual(first["state"], "ARGUMENT")
        self.assertEqual(second["state"], "EMPHASIS")
        self.assertEqual(len(result["returns"]), 1)
        self.assertEqual(result["returns"][0]["parent_event_id"], "peak")

    def test_renderer_emits_the_automatic_return_command(self):
        result = plan(payload([event("beat", 1000, 3000)]))
        commands = _commands(result)
        return_ms = result["returns"][0]["start_ms"]
        self.assertIn(f"{return_ms / 1000.0:.6f} crop@thz", commands)


if __name__ == "__main__":
    unittest.main()
