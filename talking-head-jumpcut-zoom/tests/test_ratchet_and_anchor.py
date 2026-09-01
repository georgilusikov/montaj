#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from zoom_planner import plan, _crop_for_scale_with_anchor


class TestRatchetAndAnchor(unittest.TestCase):
    def test_eye_anchor_formula(self):
        width = 1080
        height = 1920
        rows = [{"face_cx": 0.5, "face_cy": 0.35, "eye_line_y": 0.30, "face_ratio": 0.28}]
        scale = 1.20
        x, y, w, h = _crop_for_scale_with_anchor(rows, width, height, scale)
        self.assertEqual(w, 900)
        self.assertEqual(h, 1600)
        self.assertAlmostEqual(y, 96, delta=4)

    def test_ratchet_escalation(self):
        payload = {
            "source": {"width": 1080, "height": 1920, "duration_ms": 12000, "quality_cap": 1.25},
            "config": {"intensity": "dynamic", "absolute_zoom_cap": 1.20},
            "observations": [
                {"t_ms": t, "face_cx": 0.5, "face_cy": 0.35, "face_ratio": 0.26, "ear": 0.30, "mar": 0.15}
                for t in range(0, 12000, 200)
            ],
            "semantic_events": [
                {
                    "id": "e1",
                    "t_ms": 1000,
                    "end_ms": 3000,
                    "direction": "ratchet_1",
                    "boundary_candidates": [{"ms": 1000, "word_boundary": True, "ear": 0.30, "mar": 0.15}],
                },
                {
                    "id": "e2",
                    "t_ms": 3500,
                    "end_ms": 6000,
                    "direction": "ratchet_2",
                    "boundary_candidates": [{"ms": 3500, "word_boundary": True, "ear": 0.30, "mar": 0.15}],
                },
                {
                    "id": "e3",
                    "t_ms": 6500,
                    "end_ms": 9000,
                    "direction": "ratchet_3",
                    "boundary_candidates": [{"ms": 6500, "word_boundary": True, "ear": 0.30, "mar": 0.15}],
                },
            ],
            "content_cuts_ms": [1000, 3500, 6500],
        }
        res = plan(payload)
        planned = [d for d in res["decisions"] if d["status"] == "PLANNED"]
        self.assertEqual(len(planned), 3)
        self.assertEqual(planned[0]["scale"], 1.08)
        self.assertEqual(planned[1]["scale"], 1.12)
        self.assertEqual(planned[2]["scale"], 1.16)
        self.assertTrue(len(res["returns"]) >= 1)
        self.assertEqual(res["returns"][-1]["state"], "CONTEXT")
        self.assertEqual(res["returns"][-1]["scale"], 1.0)


if __name__ == "__main__":
    unittest.main()
