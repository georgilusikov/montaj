import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_events import build_events  # noqa: E402
from simple_qc import check  # noqa: E402
from post_render_qc import _mae  # noqa: E402


def dense_words(count=24, step=500):
    words = []
    for i in range(count):
        start = i * step
        words.append({"text": f"w{i}", "start_ms": start, "end_ms": start + 300})
    return words


class SemanticContractTests(unittest.TestCase):
    def test_long_spoken_clip_without_semantics_fails_closed(self):
        payload = {"words": dense_words(24), "semantic_marks": []}
        with self.assertRaisesRegex(ValueError, "semantic_marks is empty"):
            build_events(payload)

    def test_agent_owns_why_but_not_timing(self):
        words = dense_words(24)
        result = build_events({
            "words": words,
            "semantic_marks": [{
                "id": "hook",
                "start_word": 4,
                "end_word": 7,
                "importance": 0.90,
                "direction": "peak",
                "why": "contrarian hook",
            }],
        })
        event = result["semantic_events"][0]
        self.assertEqual(event["t_ms"], words[4]["start_ms"])
        self.assertEqual(event["end_ms"], words[7]["end_ms"])
        self.assertEqual(event["direction"], "peak")
        self.assertEqual(event["semantic_source"], "agent_mark_v1")
        self.assertTrue(event["boundary_candidates"])
        self.assertTrue(all(c["word_boundary"] for c in event["boundary_candidates"]))

    def test_semantic_mark_requires_reason(self):
        with self.assertRaisesRegex(ValueError, "non-empty why"):
            build_events({
                "words": dense_words(24),
                "semantic_marks": [{
                    "start_word": 2,
                    "importance": 0.8,
                }],
            })

    def test_qc_rejects_long_semantic_noop(self):
        report = check({
            "source": {"width": 1080, "height": 1920, "duration_ms": 115000},
            "config": {"semantic_contract_required": True},
            "decisions": [{
                "event_id": "important",
                "status": "KEEP",
                "desired_state": "ARGUMENT",
                "state": "CONTEXT",
                "reason": "no_safe_boundary",
            }],
        })
        checks = {e["check"] for e in report["errors"]}
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("no_visible_framing_changes", checks)
        self.assertIn("semantic_accent_became_noop", checks)

    def test_qc_rejects_missing_semantic_pass_on_long_video(self):
        report = check({
            "source": {"width": 1080, "height": 1920, "duration_ms": 115000},
            "config": {"semantic_contract_required": True},
            "decisions": [],
        })
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(e["check"] == "missing_semantic_events" for e in report["errors"]))

    def test_explicit_override_allows_intentional_no_zoom(self):
        report = check({
            "source": {"width": 1080, "height": 1920, "duration_ms": 115000},
            "config": {
                "semantic_contract_required": True,
                "allow_no_visible_framing": True,
            },
            "decisions": [],
        })
        self.assertEqual(report["status"], "PASS")

    def test_frame_mae(self):
        self.assertEqual(_mae(bytes([0, 10, 20]), bytes([0, 10, 20])), 0.0)
        self.assertAlmostEqual(_mae(bytes([0, 10]), bytes([10, 0])), 10.0)


if __name__ == "__main__":
    unittest.main()
