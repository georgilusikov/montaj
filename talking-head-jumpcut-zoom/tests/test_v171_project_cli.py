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
        self.assertEqual(a["validation"]["coverage_gap_count"], 0)
        self.assertEqual(a["validation"]["framing_coverage"], 1.0)
        self.assertEqual(a["validation"]["home_return_violation_count"], 0)
        self.assertIsNotNone(a["validation"]["state_balance"])
        self.assertEqual(a["decision_summary"][0]["status"], "PLANNED")
        framing = a["manifest"]["framing_decisions"]
        self.assertTrue(all(item.time_basis == "output" for item in framing))
        semantic = [item for item in framing if not item.derived.get("coverage_generated")]
        coverage = [item for item in framing if item.derived.get("coverage_generated")]
        self.assertEqual(len(semantic), 1)
        self.assertEqual(len(coverage), 2)
        self.assertEqual(a["manifest"]["provenance"]["framing_coverage_policy"], "explicit_source_base_v1")

    def test_hook_uses_no_wide_boost_and_caps_scale_at_116(self):
        data = payload()
        data["config"].update(
            {
                "intensity": "dynamic",
                "wide_boost": True,
                "wide_boost_cap": 1.35,
            }
        )
        data["semantic_events"][0]["context"]["is_hook"] = True
        result = plan_project(data)
        semantic = [
            item
            for item in result["manifest"]["framing_decisions"]
            if not item.derived.get("coverage_generated")
        ]
        self.assertEqual(len(semantic), 1)
        decision = semantic[0]
        self.assertLessEqual(float(decision.derived["motion_end_scale"]), 1.16)
        self.assertEqual(decision.derived["hook_scale_cap"], 1.16)
        self.assertFalse(decision.derived["wide_boost_allowed"])
        self.assertTrue(result["decision_summary"][0]["is_hook"])
        provenance = result["manifest"]["provenance"]
        self.assertEqual(provenance["hook_scale_cap"], 1.16)
        self.assertIn("hook_geometry_output_hash", provenance)

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
