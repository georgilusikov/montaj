#!/usr/bin/env python3
import unittest
import sys
import tempfile
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from speech_cleanup import plan_cleanup, export_srt


class TestSpeechCleanupAndSRT(unittest.TestCase):
    def test_plan_cleanup_removes_dead_air(self):
        payload = {
            "source": {"duration_ms": 10000},
            "config": {
                "mode": "strict",
                "cut_threshold_ms": 500,
                "target_gap_ms": 180,
                "head_pad_ms": 100,
                "tail_pad_ms": 200,
                "word_pre_pad_ms": 40,
                "word_post_pad_ms": 60,
            },
            "words": [
                {"text": "Привет", "start_ms": 500, "end_ms": 1200},
                {"text": "мир", "start_ms": 5000, "end_ms": 5600},
            ],
        }
        res = plan_cleanup(payload)
        self.assertEqual(len(res["kept_segments"]), 2)
        self.assertEqual(len(res["removed_gaps"]), 1)
        self.assertTrue(len(res["content_cuts_ms"]) == 1)
        self.assertLess(res["output_duration_ms"], 10000)
        self.assertEqual(len(res["output_words"]), 2)
        self.assertEqual(res["output_words"][0]["text"], "Привет")
        self.assertEqual(res["output_words"][1]["text"], "мир")

    def test_export_srt(self):
        output_words = [
            {"text": "Первое", "start_ms": 100, "end_ms": 400},
            {"text": "правило", "start_ms": 450, "end_ms": 800},
            {"text": "монтажа", "start_ms": 850, "end_ms": 1300},
            {"text": "держи", "start_ms": 1500, "end_ms": 1800},
            {"text": "ритм", "start_ms": 1850, "end_ms": 2200},
        ]
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            export_srt(output_words, tmp_path, max_words_per_card=3)
            content = tmp_path.read_text(encoding="utf-8")
            self.assertIn("1\n00:00:00,100 -->", content)
            self.assertIn("Первое правило монтажа", content)
            self.assertIn("2\n00:00:01,500 -->", content)
            self.assertIn("держи ритм", content)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
