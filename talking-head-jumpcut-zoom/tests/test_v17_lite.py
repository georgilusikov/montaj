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

    def test_qc_rejects_non_hold_noop(self):
        bad = {
            "source": {"width": 1080, "height": 1920},
            "decisions": [
                {
                    "status": "PLANNED",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "motion": "step",
                    "crop_start": [0, 0, 1080, 1920],
                    "crop_end": [0, 0, 1080, 1920],
                }
            ],
        }
        report = check(bad)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item["check"] == "noop_zoom" for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
