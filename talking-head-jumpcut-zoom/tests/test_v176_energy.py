import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from simple_qc import check  # noqa: E402
from zoom_planner_energy_v176 import ZOOM_LEVELS, plan  # noqa: E402


def observations(duration_ms=20000):
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
            "flow_speed_px": 0.3,
            "head_return": t % 1000 == 0,
        }
        for t in range(0, duration_ms + 1, 200)
    ]


def event(event_id, at_ms, importance, *, block_id="b", direction=None, duration_ms=1000):
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
        "accent_word": "key",
        "boundary_candidates": [
            {
                "id": f"{event_id}_b",
                "ms": at_ms,
                "word_boundary": True,
                "ear": 0.30,
                "mar": 0.20,
            }
        ],
    }
    if direction:
        row["direction"] = direction
    return row


def payload(duration_ms=16000, events=None):
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


class ResearchAlignedEnergyDirectorTests(unittest.TestCase):
    def test_ab_profile_keeps_subtle_steps_and_restores_113_peak(self):
        self.assertEqual(
            ZOOM_LEVELS,
            {"Z1": 1.03, "Z2": 1.05, "Z3": 1.08, "Z4": 1.13},
        )

    def test_opening_motion_is_not_mandatory_without_semantics(self):
        result = plan(payload(12000))
        self.assertEqual(result["version"], "1.7.6-research-aligned")
        self.assertEqual(result["intro_energy_events_added"], 0)
        self.assertEqual(result["energy_checkpoints_added"], 0)
        self.assertEqual(result["generated_energy_events"], 0)
        self.assertEqual(result["intro_energy_movement"], "SEMANTIC_ONLY")
        self.assertFalse(any(d.get("energy_generated") for d in result["decisions"]))

    def test_long_static_gap_creates_request_not_camera_move(self):
        result = plan(payload(14000))
        self.assertEqual(result["cadence_low_level_changes"], 0)
        self.assertTrue(result["refresh_requests"])
        self.assertFalse(any(d.get("cadence_refresh") for d in result["decisions"]))
        self.assertTrue(all(r.get("semantic_trigger") is False for r in result["refresh_requests"]))
        self.assertTrue(all(r.get("fallback_action") == "hold" for r in result["refresh_requests"]))

    def test_energy_does_not_replace_semantic_importance_as_scale_driver(self):
        result = plan(payload(12000, [
            event("base", 3000, 0.50, block_id="arc"),
            event("rise", 7000, 0.62, block_id="arc"),
        ]))
        rise = next(d for d in result["decisions"] if d.get("event_id") == "rise")
        self.assertEqual(rise.get("zoom_level"), "Z2")
        self.assertAlmostEqual(float(rise.get("importance")), 0.62, places=4)
        self.assertEqual(rise.get("energy_role"), "motion_only")

    def test_gradual_energy_rise_prefers_slow_push_and_peak_stays_step(self):
        result = plan(payload(16000, [
            event("base", 3000, 0.60, block_id="arc", duration_ms=2200),
            event("rise", 7000, 0.72, block_id="arc", duration_ms=3000),
            event("peak", 11500, 0.95, block_id="arc", direction="peak", duration_ms=1800),
        ]))
        rise = next(d for d in result["decisions"] if d.get("event_id") == "rise")
        peak = next(d for d in result["decisions"] if d.get("event_id") == "peak")
        self.assertEqual(rise.get("energy_trend"), "rise")
        self.assertEqual(rise.get("motion"), "slow_push")
        self.assertGreaterEqual(int(rise.get("slow_push_settle_ms", 0)), 900)
        self.assertEqual(peak.get("zoom_level"), "Z4")
        self.assertEqual(peak.get("motion"), "step")
        self.assertLessEqual(float(peak.get("scale", 1.0)), 1.13)

    def test_sharp_energy_rise_is_step_not_slow_push(self):
        result = plan(payload(12000, [
            event("base", 3000, 0.45, block_id="a"),
            event("jump", 7000, 0.90, block_id="b"),
        ]))
        jump = next(d for d in result["decisions"] if d.get("event_id") == "jump")
        self.assertEqual(jump.get("energy_trend"), "rise_fast")
        self.assertEqual(jump.get("motion"), "step")

    def test_real_peak_can_arrive_inside_old_three_second_floor(self):
        result = plan(payload(10000, [
            event("argument", 4000, 0.62, block_id="arc"),
            event("peak", 5800, 0.95, block_id="arc", direction="peak"),
        ]))
        argument = next(d for d in result["decisions"] if d.get("event_id") == "argument")
        peak = next(d for d in result["decisions"] if d.get("event_id") == "peak")
        self.assertNotEqual(argument.get("motion"), "hold")
        self.assertNotEqual(peak.get("motion"), "hold")
        gap = int(peak["start_ms"]) - int(argument["start_ms"])
        self.assertGreaterEqual(gap, 1200)
        self.assertLess(gap, 3000)

    def test_semantic_plan_passes_qc_with_113_artistic_cap(self):
        result = plan(payload(12000, [
            event("argument", 3000, 0.70, block_id="a"),
            event("peak", 7500, 0.95, block_id="b", direction="peak"),
        ]))
        report = check(result)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(result["config"]["absolute_zoom_cap"], 1.13)
        self.assertEqual(result["config"]["editorial_energy_role"], "motion_only")
        self.assertFalse(result["config"]["mandatory_opening_motion"])
        self.assertFalse(result["config"]["cadence_materializes_zoom"])


if __name__ == "__main__":
    unittest.main()
