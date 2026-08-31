import json
from pathlib import Path
import tempfile
import unittest

from thz_planner.cli import main as cli_main
from thz_planner.project import plan_project
from thz_planner.schema import canonical_json


def payload():
    observations = [
        {
            "t_ms": t,
            "face_ratio": 0.30,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "hair_top": 0.15,
            "bottom_keep_y": 0.72,
        }
        for t in range(0, 3000, 250)
    ]
    return {
        "analysis": {
            "quality": {"width": 1080, "height": 1920, "sharpness": 1.0, "noise": 0.0, "compression": 0.0},
            "observations": observations,
        },
        "config": {
            "source_type": "live",
            "pace": "neutral",
            "intensity": "moderate",
            "window_ms": 500,
            "wide_boost": False,
        },
        "initial_state": "CONTEXT",
        "initial_scale": 1.0,
        "content_edits": [
            {
                "segment_id": "keep_01",
                "src_start_ms": 0,
                "src_end_ms": 3000,
                "out_start_ms": 0,
                "out_end_ms": 3000,
            }
        ],
        "semantic_events": [
            {
                "event_id": "evt_01",
                "segment_id": "frame_01",
                "t_ms": 500,
                "requested_end_ms": 1400,
                "context": {
                    "semantic_weight": 1.0,
                    "salience": 1.0,
                    "prosody": 1.0,
                    "narrative": 0.0,
                    "theme_tag": "warning",
                    "act_reset": False,
                },
                "boundary_candidates": [
                    {
                        "candidate_id": "b1",
                        "ms": 600,
                        "semantic_fit": 1.0,
                        "word_boundary": True,
                    }
                ],
            }
        ],
    }


class ProjectPlannerTests(unittest.TestCase):
    def test_full_project_is_byte_stable(self):
        a = plan_project(payload())
        b = plan_project(payload())
        self.assertEqual(canonical_json(a), canonical_json(b))
        self.assertEqual(a["validation"]["status"], "PASS")
        self.assertEqual(a["decision_summary"][0]["status"], "PLANNED")
        framing = a["manifest"]["framing_decisions"][0]
        self.assertEqual(framing.time_basis, "output")

    def test_cli_writes_canonical_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.json"
            dst = Path(tmp) / "output.json"
            src.write_text(json.dumps(payload(), ensure_ascii=False), encoding="utf-8")
            self.assertEqual(cli_main([str(src), str(dst)]), 0)
            first = dst.read_text(encoding="utf-8")
            self.assertTrue(first.endswith("\n"))
            cli_main([str(src), str(dst)])
            self.assertEqual(first, dst.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
