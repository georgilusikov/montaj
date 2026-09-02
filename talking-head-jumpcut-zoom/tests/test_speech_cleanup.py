import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from speech_cleanup import classify_family, plan_cleanup  # noqa: E402


class SpeechCleanupTests(unittest.TestCase):
    def test_short_pause_is_preserved(self):
        payload = {
            "source": {"duration_ms": 3000},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 680, "end_ms": 980},
            ],
        }
        result = plan_cleanup(payload)
        self.assertEqual(result["family"], "A")
        self.assertFalse(result["pause_cleanup_enabled"])
        self.assertEqual(len(result["kept_segments"]), 1)
        self.assertEqual(result["content_cuts_ms"], [])
        segment = result["kept_segments"][0]
        self.assertEqual(segment["src_start_ms"], 0)
        self.assertEqual(segment["src_end_ms"], 3000)

    def test_ambiguous_single_long_pause_fails_safe_to_family_a(self):
        payload = {
            "source": {"duration_ms": 3000},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 1500, "end_ms": 1800},
            ],
        }
        result = plan_cleanup(payload)
        self.assertEqual(result["family"], "A")
        self.assertTrue(result["family_metrics"]["ambiguous"])
        self.assertFalse(result["pause_cleanup_enabled"])
        self.assertEqual(result["removed_gaps"], [])

    def test_auto_family_b_requires_repeated_air(self):
        words = [
            {"text": "a", "start_ms": 0, "end_ms": 200},
            {"text": "b", "start_ms": 800, "end_ms": 1000},
            {"text": "c", "start_ms": 1600, "end_ms": 1800},
        ]
        family, metrics = classify_family(words, {})
        self.assertEqual(family, "B")
        self.assertEqual(metrics["gaps_over_450"], 2)

    def test_family_b_default_preserves_450ms_and_trims_only_longer_pauses(self):
        payload = {
            "source": {"duration_ms": 4500},
            "config": {"family": "B"},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 1100, "end_ms": 1400},
                {"text": "three", "start_ms": 2000, "end_ms": 2300},
            ],
        }
        result = plan_cleanup(payload)
        self.assertTrue(result["pause_cleanup_enabled"])
        self.assertEqual(result["config"]["cut_threshold_ms"], 450)
        self.assertEqual(result["config"]["target_gap_ms"], 450)
        self.assertEqual(len(result["kept_segments"]), 3)
        self.assertTrue(all(g["remaining_gap_ms"] == 450 for g in result["removed_gaps"]))

    def test_family_b_pause_at_450_is_not_cut(self):
        payload = {
            "source": {"duration_ms": 2500},
            "config": {"family": "B"},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 950, "end_ms": 1250},
            ],
        }
        result = plan_cleanup(payload)
        self.assertEqual(len(result["kept_segments"]), 1)
        self.assertEqual(result["removed_gaps"], [])
        self.assertEqual(result["content_cuts_ms"], [])

    def test_long_pause_is_reduced_to_target_gap_when_explicit(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {"cut_threshold_ms": 500, "target_gap_ms": 180},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 1500, "end_ms": 1800},
            ],
        }
        result = plan_cleanup(payload)
        self.assertEqual(len(result["kept_segments"]), 2)
        removed = result["removed_gaps"][0]
        self.assertEqual(removed["original_gap_ms"], 1000)
        self.assertEqual(removed["remaining_gap_ms"], 180)
        self.assertEqual(removed["removed_ms"], 820)

    def test_output_mapping_and_content_cut_are_contiguous(self):
        payload = {
            "source": {"duration_ms": 4000},
            "config": {"family": "B", "cut_threshold_ms": 500, "target_gap_ms": 180},
            "words": [
                {"text": "a", "start_ms": 200, "end_ms": 500},
                {"text": "b", "start_ms": 1500, "end_ms": 1800},
                {"text": "c", "start_ms": 2100, "end_ms": 2400},
            ],
        }
        result = plan_cleanup(payload)
        first, second = result["kept_segments"]
        self.assertEqual(first["out_start_ms"], 0)
        self.assertEqual(second["out_start_ms"], first["out_end_ms"])
        self.assertEqual(result["content_cuts_ms"], [second["out_start_ms"]])

    def test_words_are_remapped_to_calmer_dense_output_timeline(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {"family": "B"},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 1500, "end_ms": 1800},
            ],
        }
        result = plan_cleanup(payload)
        first, second = result["output_words"]
        self.assertEqual(first["source_start_ms"], 200)
        self.assertEqual(second["source_start_ms"], 1500)
        self.assertLess(second["start_ms"], second["source_start_ms"])
        self.assertEqual(second["start_ms"] - first["end_ms"], 450)

    def test_family_a_preserves_original_word_timing(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {"family": "A"},
            "words": [
                {"text": "one", "start_ms": 200, "end_ms": 500},
                {"text": "two", "start_ms": 1500, "end_ms": 1800},
            ],
        }
        result = plan_cleanup(payload)
        self.assertEqual(result["content_cuts_ms"], [])
        self.assertEqual(result["output_words"][1]["start_ms"], 1500)
        self.assertEqual(result["output_duration_ms"], 3000)

    def test_head_and_tail_padding_are_kept_when_cleanup_enabled(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {
                "family": "B",
                "pause_cleanup_enabled": True,
                "head_pad_ms": 120,
                "tail_pad_ms": 350,
            },
            "words": [
                {"text": "hello", "start_ms": 500, "end_ms": 800},
                {"text": "world", "start_ms": 1000, "end_ms": 1300},
            ],
        }
        result = plan_cleanup(payload)
        segment = result["kept_segments"][0]
        self.assertEqual(segment["src_start_ms"], 380)
        self.assertEqual(segment["src_end_ms"], 1650)

    def test_strict_mode_only(self):
        with self.assertRaises(ValueError):
            plan_cleanup(
                {
                    "source": {"duration_ms": 1000},
                    "config": {"mode": "clean_speech"},
                    "words": [{"text": "x", "start_ms": 100, "end_ms": 500}],
                }
            )


if __name__ == "__main__":
    unittest.main()
