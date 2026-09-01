#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from simple_qc import check  # noqa: E402
from zoom_planner import plan  # noqa: E402


class HeadroomAndZoomCapTests(unittest.TestCase):
    def _payload(self):
        observations = []
        for t in range(0, 5001, 200):
            observations.append(
                {
                    "t_ms": t,
                    "face_ratio": 0.20,
                    "face_cx": 0.50,
                    "face_cy": 0.34,
                    "eye_line_y": 0.38,
                    "hair_top": 0.10,
                    "ear": 0.30,
                    "mar": 0.15,
                    "caption_overlap": 0.0,
                }
            )
        # Highest head position during the anticipated zoom episode. Eye anchoring alone
        # would place the crop too low; restored segment-wide headroom must move it up.
        observations[7]["hair_top"] = 0.08  # t=1400 ms
        return {
            "source": {"width": 1080, "height": 1920, "duration_ms": 5000, "quality_cap": 1.40},
            "config": {"intensity": "dynamic", "absolute_zoom_cap": 1.20, "window_ms": 600},
            "observations": observations,
            "semantic_events": [
                {
                    "id": "peak",
                    "t_ms": 1000,
                    "end_ms": 3300,
                    "importance": 0.96,
                    "direction": "peak",
                    "boundary_candidates": [
                        {"id": "b1", "ms": 1000, "word_boundary": True, "ear": 0.30, "mar": 0.15}
                    ],
                }
            ],
        }

    def test_planner_global_cap_is_113_even_if_config_requests_more(self):
        result = plan(self._payload())
        self.assertEqual(result["config"]["absolute_zoom_cap"], 1.13)
        planned = [d for d in result["decisions"] if d.get("status") == "PLANNED"]
        self.assertTrue(planned)
        self.assertTrue(all(float(d["scale"]) <= 1.13 for d in planned))

    def test_segment_wide_headroom_is_at_least_five_percent(self):
        result = plan(self._payload())
        decision = next(d for d in result["decisions"] if d.get("status") == "PLANNED")
        self.assertIsNotNone(decision.get("headroom_ratio"))
        self.assertGreaterEqual(float(decision["headroom_ratio"]), 0.048)
        self.assertEqual(result["config"]["min_headroom_ratio"], 0.05)

        _, y, _, crop_h = decision["crop_end"]
        highest_hair_px = 0.08 * 1920
        measured = (highest_hair_px - y) / crop_h
        self.assertGreaterEqual(measured, 0.048)

    def test_qc_rejects_ratchet_above_113(self):
        bad = {
            "source": {"width": 1080, "height": 1920, "duration_ms": 3000},
            "config": {
                "absolute_zoom_cap": 1.20,
                "state_caps": {"EMPHASIS": 1.20},
                "min_headroom_ratio": 0.05,
                "semantic_contract_required": False,
            },
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "state": "EMPHASIS",
                    "desired_state": "EMPHASIS",
                    "ratchet": "ratchet_3",
                    "scale": 1.14,
                    "headroom_ratio": 0.06,
                    "crop_start": [0, 0, 1080, 1920],
                    "crop_end": [66, 118, 948, 1684],
                }
            ],
            "cadence_requests": [],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        checks = {item["check"] for item in report["errors"]}
        self.assertIn("zoom_too_aggressive", checks)

    def test_qc_rejects_reported_headroom_below_five_percent(self):
        bad = {
            "source": {"width": 1080, "height": 1920, "duration_ms": 3000},
            "config": {"semantic_contract_required": False, "min_headroom_ratio": 0.05},
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "state": "ARGUMENT",
                    "desired_state": "ARGUMENT",
                    "scale": 1.08,
                    "headroom_ratio": 0.04,
                    "crop_start": [0, 0, 1080, 1920],
                    "crop_end": [50, 88, 1000, 1778],
                }
            ],
            "cadence_requests": [],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        checks = {item["check"] for item in report["errors"]}
        self.assertIn("headroom_too_small", checks)


if __name__ == "__main__":
    unittest.main()
