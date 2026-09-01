#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from frame_defects import calculate_ear, calculate_mar, evaluate_frame_quality
from zoom_planner import plan, _crop_for_scale_with_anchor, _crop_safe
from speech_cleanup import plan_cleanup


class EdgeCasesSelfVerification(unittest.TestCase):
    def test_edge_zero_division_ear_mar(self):
        p_zero = [[0.0, 0.0] for _ in range(6)]
        ear = calculate_ear(p_zero)
        mar = calculate_mar(p_zero)
        self.assertEqual(ear, 0.0)
        self.assertEqual(mar, 0.0)

    def test_edge_empty_observations_fallback(self):
        obs = {"t_ms": 100}
        is_clean, reasons = evaluate_frame_quality(obs)
        self.assertTrue(is_clean)
        self.assertEqual(reasons, [])

    def test_edge_scale_1_exact(self):
        crop = _crop_for_scale_with_anchor([{"face_cx": 0.5}], 1080, 1920, 1.0)
        self.assertEqual(crop, (0, 0, 1080, 1920))

    def test_edge_face_near_boundary_clamping(self):
        rows_left = [{"face_cx": 0.05, "face_cy": 0.10, "eye_line_y": 0.08}]
        x, y, w, h = _crop_for_scale_with_anchor(rows_left, 1080, 1920, 1.20)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, 1080)
        self.assertLessEqual(y + h, 1920)

    def test_edge_speech_cleanup_no_words(self):
        payload = {"source": {"duration_ms": 5000}, "config": {"mode": "strict"}, "words": []}
        res = plan_cleanup(payload)
        self.assertEqual(res["output_duration_ms"], 5000)
        self.assertEqual(len(res["kept_segments"]), 1)
        self.assertEqual(len(res["removed_gaps"]), 0)

    def test_edge_speech_cleanup_continuous_speech_no_gaps(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {"mode": "strict", "cut_threshold_ms": 500},
            "words": [
                {"text": "слово", "start_ms": 100, "end_ms": 600},
                {"text": "два", "start_ms": 700, "end_ms": 1200},
                {"text": "три", "start_ms": 1300, "end_ms": 1800},
            ],
        }
        res = plan_cleanup(payload)
        self.assertEqual(len(res["removed_gaps"]), 0)
        self.assertEqual(len(res["kept_segments"]), 1)


if __name__ == "__main__":
    unittest.main()
