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


def event(event_id, t_ms, end_ms, *, direction="build", importance=0.70, motion_hint=None):
    row = {
        "id": event_id,
        "t_ms": t_ms,
        "end_ms": end_ms,
        "importance": importance,
        "direction": direction,
        "boundary_candidates": [{"id": f"b-{event_id}", "ms": t_ms, "word_boundary": True}],
    }
    if motion_hint:
        row["motion_hint"] = motion_hint
    return row


def payload(events, duration_ms=12000, cuts=None):
    return {
        "source": {"width": 2160, "height": 3840, "quality_cap": 1.60, "duration_ms": duration_ms},
        "config": {"intensity": "moderate", "window_ms": 600},
        "observations": observations(duration_ms),
        "semantic_events": events,
        "content_cuts_ms": cuts or [],
    }


class VisualRhythmTests(unittest.TestCase):
    def test_normal_build_is_not_automatically_slow(self):
        result = plan(payload([event("build", 1000, 4000, direction="build", importance=0.80)], duration_ms=5000))
        decision = result["decisions"][0]
        self.assertEqual(decision["state"], "ARGUMENT")
        self.assertFalse(decision["soft_build"])
        self.assertEqual(decision["motion"], "step")
        self.assertAlmostEqual(decision["scale"], 1.12, places=2)

    def test_explicit_gradual_build_uses_soft_slow_push(self):
        result = plan(payload([
            event("build", 1000, 4000, direction="build", importance=0.80, motion_hint="slow_push")
        ], duration_ms=5000))
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

    def test_long_neutral_gap_requests_jumpcut_instead_of_camera_drift(self):
        result = plan(payload([], duration_ms=12000))
        self.assertNotIn("refreshes", result)
        self.assertGreaterEqual(len(result["cadence_requests"]), 2)
        first = result["cadence_requests"][0]
        self.assertEqual(first["preferred_action"], "jumpcut_same_scale")
        self.assertFalse(first["semantic_trigger"])
        self.assertLessEqual(first["at_ms"], 5000)
        self.assertEqual(check(result)["status"], "PASS")

    def test_existing_content_cuts_satisfy_visual_cadence(self):
        result = plan(payload([], duration_ms=12000, cuts=[3500, 7000, 10500]))
        self.assertEqual(result["cadence_requests"], [])

    def test_slow_push_renderer_uses_dense_interpolation(self):
        result = plan(payload([
            event("build", 1000, 4000, direction="build", importance=0.80, motion_hint="slow_push")
        ], duration_ms=5000))
        commands = _commands(result)
        # 2.4 s at 60 Hz yields far more than the old 10 Hz stair-step command stream.
        self.assertGreater(commands.count("crop@thz w"), 100)


if __name__ == "__main__":
    unittest.main()
