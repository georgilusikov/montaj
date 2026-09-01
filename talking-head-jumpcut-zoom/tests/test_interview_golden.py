import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from semantic_events import build_events  # noqa: E402
from zoom_planner import plan  # noqa: E402
from simple_qc import check  # noqa: E402


DURATION_MS = 115000
STEP_MS = 500


def dense_words():
    count = DURATION_MS // STEP_MS
    words = []
    labels = {
        0: "Nunca se apresente assim",
        36: "Isso não é uma apresentação",
        58: "não é uma formalidade",
        74: "Uma ótima resposta",
        116: "Algo assim",
        162: "Sessenta segundos",
        188: "primeiros trinta segundos",
        220: "princípios",
    }
    for i in range(count):
        start = i * STEP_MS
        words.append({
            "text": labels.get(i, f"w{i}"),
            "start_ms": start,
            "end_ms": start + 320,
        })
    return words


def observations():
    return [
        {
            "t_ms": t,
            "face_ratio": 0.22,
            "face_cx": 0.50,
            "face_cy": 0.34,
            "eye_line_y": 0.29,
            "hair_top": 0.12,
            "caption_overlap": 0.0,
            "ear": 0.30,
            "mar": 0.20,
            "laplacian_var": 120.0,
            "flow_speed_px": 0.4,
        }
        for t in range(0, DURATION_MS + 1, 250)
    ]


class InterviewGoldenRegression(unittest.TestCase):
    def test_two_minute_interview_structure_cannot_collapse_to_constant_100_percent(self):
        words = dense_words()
        semantic = build_events({
            "words": words,
            "semantic_marks": [
                {
                    "id": "hook",
                    "start_word": 0,
                    "end_word": 5,
                    "importance": 0.78,
                    "direction": "build",
                    "why": "contrarian opening instruction",
                },
                {
                    "id": "correction",
                    "start_word": 36,
                    "end_word": 42,
                    "importance": 0.76,
                    "direction": "build",
                    "why": "sharp correction: presentation is not a CV readout",
                },
                {
                    "id": "first_test",
                    "start_word": 58,
                    "end_word": 64,
                    "importance": 0.95,
                    "direction": "peak",
                    "why": "core claim: this question is the first test",
                },
                {
                    "id": "method",
                    "start_word": 74,
                    "end_word": 80,
                    "importance": 0.78,
                    "direction": "build",
                    "why": "transition into the recommended answer structure",
                },
                {
                    "id": "example_reset",
                    "start_word": 116,
                    "end_word": 120,
                    "importance": 0.30,
                    "direction": "release",
                    "why": "reset before the concrete example",
                },
                {
                    "id": "sixty_seconds",
                    "start_word": 162,
                    "end_word": 165,
                    "importance": 0.95,
                    "direction": "peak",
                    "why": "short numerical payoff",
                },
                {
                    "id": "first_thirty",
                    "start_word": 188,
                    "end_word": 195,
                    "importance": 0.84,
                    "direction": "build",
                    "why": "conclusion about the first thirty seconds setting the tone",
                },
                {
                    "id": "final",
                    "start_word": 220,
                    "end_word": 226,
                    "importance": 0.90,
                    "direction": "peak",
                    "why": "final takeaway / CTA beat",
                },
            ],
        })

        result = plan({
            "source": {
                "width": 2160,
                "height": 3840,
                "duration_ms": DURATION_MS,
                "quality_cap": 1.60,
            },
            "config": {"intensity": "moderate", "window_ms": 800},
            "observations": observations(),
            "semantic_events": semantic["semantic_events"],
            "content_cuts_ms": [3000, 7000, 10000, 18000, 23000, 29000, 37000, 49000, 58000, 72000, 81000, 94000, 102000],
        })

        report = check(result)
        visible = [
            d for d in result["decisions"]
            if d.get("status") == "PLANNED"
            and d.get("motion") != "hold"
            and d.get("crop_start") != d.get("crop_end")
        ]

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(semantic["semantic_event_count"], 8)
        self.assertGreaterEqual(len(visible), 5)
        self.assertTrue(any(d.get("state") == "EMPHASIS" for d in visible))
        self.assertTrue(any(d.get("state") == "ARGUMENT" for d in visible))


if __name__ == "__main__":
    unittest.main()
