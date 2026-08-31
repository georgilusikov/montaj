import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from zoom_planner import plan  # noqa: E402
from simple_qc import check  # noqa: E402


def observations(face_ratio=0.30):
    return [
        {
            "t_ms": t,
            "face_ratio": face_ratio,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
        }
        for t in range(0, 4000, 250)
    ]


def payload(*, importance=1.0, face_ratio=0.30, candidates=None):
    return {
        "source": {"width": 1080, "height": 1920, "quality_cap": 1.16},
        "config": {"intensity": "moderate", "window_ms": 1000},
        "observations": observations(face_ratio),
        "semantic_events": [
            {
                "id": "e1",
                "t_ms": 1000,
                "end_ms": 2200,
                "importance": importance,
                "boundary_candidates": candidates
                or [
                    {"id": "b1", "ms": 1050, "word_boundary": True},
                ],
            }
        ],
    }


class LitePlannerTests(unittest.TestCase):
    def test_head_return_cannot_create_semantic_emphasis(self):
        result = plan(
            payload(
                importance=0.10,
                candidates=[{"id": "look", "ms": 1000, "head_return": True, "word_boundary": True}],
            )
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["desired_state"], "CONTEXT")
        self.assertEqual(decision["state"], "CONTEXT")

    def test_tight_source_collapses_fake_states(self):
        result = plan(payload(importance=1.0, face_ratio=0.39))
        decision = result["decisions"][0]
        self.assertEqual(decision["available_states"], ["CONTEXT"])
        self.assertEqual(decision["state"], "CONTEXT")

    def test_redundant_argument_can_collapse_to_context_emphasis(self):
        result = plan(payload(importance=1.0, face_ratio=0.30))
        decision = result["decisions"][0]
        self.assertEqual(decision["available_states"], ["CONTEXT", "EMPHASIS"])
        self.assertEqual(decision["state"], "EMPHASIS")
        self.assertLessEqual(decision["scale"], 1.16)

    def test_blink_candidate_is_rejected(self):
        result = plan(
            payload(
                candidates=[
                    {"id": "blink", "ms": 1000, "word_boundary": True, "blink": True},
                    {"id": "safe", "ms": 1200, "word_boundary": True},
                ]
            )
        )
        decision = result["decisions"][0]
        self.assertEqual(decision["start_ms"], 1200)

    def test_4k_quality_cap_does_not_raise_artistic_zoom_cap(self):
        data = payload(importance=1.0, face_ratio=0.20)
        data["source"] = {"width": 2160, "height": 3840, "quality_cap": 1.60}
        data["config"]["intensity"] = "dynamic"
        result = plan(data)
        decision = result["decisions"][0]
        self.assertLessEqual(decision["scale"], 1.20)
        self.assertLessEqual(decision["state_cap"], 1.20)

    def test_argument_has_stricter_cap_than_emphasis(self):
        data = payload(importance=0.60, face_ratio=0.20)
        data["source"] = {"width": 2160, "height": 3840, "quality_cap": 1.60}
        data["config"]["intensity"] = "dynamic"
        result = plan(data)
        decision = result["decisions"][0]
        self.assertEqual(decision["desired_state"], "ARGUMENT")
        self.assertLessEqual(decision["scale"], 1.12)

    def test_qc_rejects_non_hold_noop(self):
        bad = {
            "source": {"width": 1080, "height": 1920},
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "state": "CONTEXT",
                    "crop_start": [0, 0, 1080, 1920],
                    "crop_end": [0, 0, 1080, 1920],
                }
            ],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item["check"] == "noop_zoom" for item in report["errors"]))

    def test_qc_rejects_old_160x_emphasis_plan(self):
        bad = {
            "source": {"width": 2160, "height": 3840},
            "config": {"absolute_zoom_cap": 1.20},
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "state": "EMPHASIS",
                    "scale": 1.60,
                    "crop_start": [0, 0, 2160, 3840],
                    "crop_end": [405, 720, 1350, 2400],
                }
            ],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        checks = {item["check"] for item in report["errors"]}
        self.assertIn("zoom_too_aggressive", checks)
        self.assertIn("crop_scale_too_aggressive", checks)

    def test_qc_rejects_old_133x_argument_plan(self):
        bad = {
            "source": {"width": 2160, "height": 3840},
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "state": "ARGUMENT",
                    "scale": 1.33,
                    "crop_start": [0, 0, 2160, 3840],
                    "crop_end": [268, 477, 1624, 2886],
                }
            ],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item["check"] == "zoom_too_aggressive" for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
