#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from frame_defects import calculate_ear, calculate_mar, evaluate_frame_quality


class TestFrameDefects(unittest.TestCase):
    def test_calculate_ear_open_eye(self):
        eye_open = [
            [0.0, 0.0],
            [2.0, 3.0],
            [4.0, 3.0],
            [6.0, 0.0],
            [4.0, -3.0],
            [2.0, -3.0],
        ]
        ear = calculate_ear(eye_open)
        self.assertAlmostEqual(ear, 1.0, places=2)

    def test_calculate_ear_closed_eye(self):
        eye_closed = [
            [0.0, 0.0],
            [2.0, 0.2],
            [4.0, 0.2],
            [6.0, 0.0],
            [4.0, -0.2],
            [2.0, -0.2],
        ]
        ear = calculate_ear(eye_closed)
        self.assertLess(ear, 0.15)

    def test_calculate_mar_open_mouth(self):
        mouth_open = [
            [0.0, 0.0],
            [2.0, 3.0],
            [4.0, 3.0],
            [6.0, 0.0],
            [4.0, -3.0],
            [2.0, -3.0],
        ]
        mar = calculate_mar(mouth_open)
        self.assertAlmostEqual(mar, 1.0, places=2)

    def test_evaluate_frame_quality_clean(self):
        obs = {
            "ear": 0.32,
            "mar": 0.20,
            "laplacian_var": 120.0,
            "flow_speed_px": 0.4,
            "pose_unsafe": False,
        }
        is_clean, reasons = evaluate_frame_quality(obs)
        self.assertTrue(is_clean)
        self.assertEqual(reasons, [])

    def test_evaluate_frame_quality_blink_and_blur(self):
        obs = {
            "ear": 0.14,
            "mar": 0.18,
            "laplacian_var": 32.0,
            "flow_speed_px": 3.5,
        }
        is_clean, reasons = evaluate_frame_quality(obs)
        self.assertFalse(is_clean)
        self.assertIn("blink_ear", reasons)
        self.assertIn("motion_blur", reasons)
        self.assertIn("high_motion_velocity", reasons)


if __name__ == "__main__":
    unittest.main()
