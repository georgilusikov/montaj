import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline_guard import check_final, check_pre_render  # noqa: E402
from render_zoom import validate_guard  # noqa: E402
from visual_evidence import build_review_groups  # noqa: E402
from visual_scan import _largest_box  # noqa: E402


def good_artifacts():
    cleanup = {
        "version": "1.7.1-lite",
        "output_words": [{"text": "hello", "start_ms": 0, "end_ms": 300}],
        "content_cuts_ms": [1800],
    }
    semantic = {
        "version": "1.7.1-lite",
        "semantic_event_count": 1,
        "semantic_events": [{"id": "hook", "t_ms": 1000}],
    }
    scan = {
        "version": "1.7.2-lite",
        "face_coverage": 0.95,
        "observations": [{"t_ms": 0, "face_ratio": 0.3}],
    }
    plan = {
        "decisions": [{
            "event_id": "hook",
            "status": "PLANNED",
            "start_ms": 1000,
            "motion": "step",
            "state": "ARGUMENT",
            "scale": 1.1,
            "crop_start": [0, 0, 1080, 1920],
            "crop_end": [48, 86, 982, 1746],
        }],
        "returns": [],
    }
    pre_qc = {"status": "PASS"}
    manifest = {
        "phase": "pre",
        "required_group_ids": ["jumpcut_00001800", "zoom_00001000"],
    }
    review = {
        "status": "PASS",
        "reviewer": "vision_model",
        "reviewed_groups": [
            {"id": "jumpcut_00001800", "verdict": "PASS"},
            {"id": "zoom_00001000", "verdict": "PASS"},
        ],
    }
    return cleanup, semantic, scan, plan, pre_qc, manifest, review


class VisualEvidenceTests(unittest.TestCase):
    def test_review_groups_cover_content_cut_and_visible_zoom(self):
        cleanup, _, _, plan, _, _, _ = good_artifacts()
        groups = build_review_groups(plan, cleanup)
        kinds = [g["kind"] for g in groups]
        self.assertIn("jumpcut", kinds)
        self.assertIn("zoom", kinds)
        self.assertTrue(all(g["required"] for g in groups))
        self.assertTrue(all(g["offsets_ms"] == [-160, 0, 160] for g in groups))

    def test_review_groups_ignore_hold_noop(self):
        plan = {
            "decisions": [{
                "status": "PLANNED",
                "start_ms": 1000,
                "motion": "hold",
                "crop_start": [0, 0, 1080, 1920],
                "crop_end": [0, 0, 1080, 1920],
            }]
        }
        self.assertEqual(build_review_groups(plan), [])

    def test_largest_box_is_deterministic(self):
        self.assertEqual(_largest_box([(0, 0, 10, 10), (1, 1, 20, 10)]), (1, 1, 20, 10))
        self.assertIsNone(_largest_box([]))


class PipelineGuardTests(unittest.TestCase):
    def test_pre_guard_passes_complete_canonical_evidence(self):
        artifacts = good_artifacts()
        report = check_pre_render(*artifacts)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["pipeline_lock"], "PASS")
        self.assertEqual(report["visual_evidence"], "PASS")
        validate_guard(report)

    def test_pre_guard_fails_without_visual_review(self):
        cleanup, semantic, scan, plan, pre_qc, manifest, review = good_artifacts()
        review["reviewed_groups"] = [{"id": "zoom_00001000", "verdict": "PASS"}]
        report = check_pre_render(cleanup, semantic, scan, plan, pre_qc, manifest, review)
        checks = {e["check"] for e in report["errors"]}
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("pre_visual_groups_missing", checks)
        with self.assertRaises(ValueError):
            validate_guard(report)

    def test_pre_guard_fails_transcript_only_run(self):
        cleanup, semantic, scan, plan, pre_qc, manifest, review = good_artifacts()
        scan = {"version": "1.7.2-lite", "face_coverage": 0.0, "observations": []}
        report = check_pre_render(cleanup, semantic, scan, plan, pre_qc, manifest, review)
        checks = {e["check"] for e in report["errors"]}
        self.assertIn("visual_observations_missing", checks)
        self.assertIn("visual_face_coverage_low", checks)

    def test_final_guard_requires_pixel_qc_and_final_visual_review(self):
        pre = {"stage": "pre-render", "status": "PASS", "pipeline_lock": "PASS", "visual_evidence": "PASS"}
        post = {"status": "PASS", "verified_change_count": 2}
        manifest = {"phase": "final", "required_group_ids": ["zoom_00001000"]}
        review = {
            "status": "PASS",
            "reviewer": "human_visual",
            "reviewed_groups": [{"id": "zoom_00001000", "verdict": "PASS"}],
        }
        report = check_final(pre, post, manifest, review)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["accepted_final"])

        post["status"] = "FAIL"
        report = check_final(pre, post, manifest, review)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["accepted_final"])


if __name__ == "__main__":
    unittest.main()
