import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zoom_planner import plan  # noqa: E402
from simple_qc import check  # noqa: E402


def _observations():
    return [
        {
            "t_ms": t,
            "face_ratio": 0.20,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
        }
        for t in range(0, 5000, 250)
    ]


class ContextSourceFramingTests(unittest.TestCase):
    def test_context_is_exact_source_frame(self):
        payload = {
            "source": {"width": 1080, "height": 1920, "quality_cap": 1.60},
            "config": {"intensity": "dynamic", "window_ms": 800},
            "observations": _observations(),
            "semantic_events": [
                {
                    "id": "context",
                    "t_ms": 500,
                    "end_ms": 1200,
                    "importance": 0.10,
                    "direction": "release",
                    "boundary_candidates": [{"id": "b1", "ms": 500, "word_boundary": True}],
                }
            ],
        }
        result = plan(payload)
        decision = result["decisions"][0]
        self.assertEqual(decision["state"], "CONTEXT")
        self.assertEqual(decision["scale"], 1.0)
        self.assertEqual(decision["crop_end"], [0, 0, 1080, 1920])
        self.assertEqual(result["config"]["state_caps"]["CONTEXT"], 1.0)
        self.assertEqual(check(result)["status"], "PASS")

    def test_zoom_auto_return_goes_to_exact_source_frame(self):
        payload = {
            "source": {"width": 1080, "height": 1920, "quality_cap": 1.60},
            "config": {"intensity": "dynamic", "window_ms": 800},
            "observations": _observations(),
            "semantic_events": [
                {
                    "id": "argument",
                    "t_ms": 500,
                    "end_ms": 2500,
                    "importance": 0.70,
                    "direction": "build",
                    "boundary_candidates": [{"id": "b1", "ms": 500, "word_boundary": True}],
                }
            ],
        }
        result = plan(payload)
        self.assertEqual(result["decisions"][0]["state"], "ARGUMENT")
        self.assertEqual(len(result["returns"]), 1)
        returned = result["returns"][0]
        self.assertEqual(returned["scale"], 1.0)
        self.assertEqual(returned["crop_end"], [0, 0, 1080, 1920])


if __name__ == "__main__":
    unittest.main()
