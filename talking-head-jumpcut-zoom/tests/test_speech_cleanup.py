import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from speech_cleanup import plan_cleanup  # noqa: E402


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
        self.assertEqual(len(result["kept_segments"]), 1)
        self.assertEqual(result["content_cuts_ms"], [])
        segment = result["kept_segments"][0]
        self.assertEqual(segment["src_start_ms"], 80)
        self.assertEqual(segment["src_end_ms"], 1330)

    def test_long_pause_is_reduced_to_target_gap(self):
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
            "config": {"cut_threshold_ms": 500, "target_gap_ms": 180},
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

    def test_words_are_remapped_to_dense_output_timeline(self):
        payload = {
            "source": {"duration_ms": 3000},
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
        self.assertEqual(second["start_ms"] - first["end_ms"], 180)

    def test_head_and_tail_padding_are_kept(self):
        payload = {
            "source": {"duration_ms": 3000},
            "config": {"head_pad_ms": 120, "tail_pad_ms": 350},
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
