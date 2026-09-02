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


class EnergyDirectorTests(unittest.TestCase):
    def test_energy_profile_uses_requested_four_steps(self):
        self.assertEqual(
            ZOOM_LEVELS,
            {"Z1": 1.03, "Z2": 1.05, "Z3": 1.08, "Z4": 1.12},
        )

    def test_first_five_seconds_get_rising_motion_even_without_semantics(self):
        result = plan(payload(12000))
        self.assertEqual(result["version"], "1.7.6-energy")
        self.assertGreaterEqual(result["intro_energy_events_added"], 1)
        self.assertEqual(result["intro_energy_movement"], "PASS")

        intro = [
            d for d in result["decisions"]
            if d.get("intro_energy") and d.get("status") == "PLANNED"
        ]
        self.assertTrue(intro)
        self.assertTrue(any(int(d["start_ms"]) < 5000 for d in intro))
        self.assertTrue(all(d.get("zoom_level") in {"Z1", "Z2"} for d in intro))
        self.assertTrue(any(d.get("motion") == "slow_push" for d in intro))

        opening_curve = [
            p for p in result["editorial_energy_curve"] if int(p["t_ms"]) <= 5000
        ]
        energies = [float(p["energy"]) for p in opening_curve]
        self.assertEqual(energies, sorted(energies))

    def test_real_semantic_event_replaces_nearby_synthetic_intro(self):
        result = plan(payload(10000, [event("hook", 1000, 0.78, block_id="hook")]))
        ids = {str(p["event_id"]) for p in result["editorial_energy_curve"]}
        self.assertIn("hook", ids)
        self.assertNotIn("energy_intro_1", ids)

    def test_rising_energy_prefers_slow_push_but_peak_stays_step(self):
        result = plan(payload(18000, [
            event("base", 7000, 0.60, block_id="arc"),
            event("rise", 11000, 0.74, block_id="arc"),
            event("peak", 15000, 0.95, block_id="arc", direction="peak"),
        ]))
        rise = next(d for d in result["decisions"] if d.get("event_id") == "rise")
        peak = next(d for d in result["decisions"] if d.get("event_id") == "peak")
        self.assertEqual(rise.get("energy_trend"), "rise")
        self.assertEqual(rise.get("motion"), "slow_push")
        self.assertEqual(peak.get("zoom_level"), "Z4")
        self.assertEqual(peak.get("motion"), "step")
        self.assertLessEqual(float(peak.get("scale", 1.0)), 1.12)

    def test_generated_energy_checkpoint_never_creates_z4(self):
        result = plan(payload(22000, [
            event("early", 6000, 0.80, block_id="a"),
            event("late", 20000, 0.90, block_id="b"),
        ]))
        generated = [
            d for d in result["decisions"]
            if d.get("energy_generated") and not d.get("intro_energy")
        ]
        self.assertTrue(generated)
        self.assertTrue(all(d.get("zoom_level") != "Z4" for d in generated))

    def test_energy_plan_still_passes_v176_qc(self):
        result = plan(payload(14000))
        report = check(result)
        self.assertEqual(report["status"], "PASS", report)
        self.assertLessEqual(result["config"]["absolute_zoom_cap"], 1.12)
        self.assertEqual(result["config"]["energy_cadence_role"], "guard_rail_only")


if __name__ == "__main__":
    unittest.main()
