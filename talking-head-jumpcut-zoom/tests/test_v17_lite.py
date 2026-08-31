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
        for t in range(0, 6000, 250)
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

    def test_emphasis_is_reserved_for_rare_high_importance_events(self):
        argument = plan(payload(importance=0.80))["decisions"][0]
        emphasis = plan(payload(importance=0.90))["decisions"][0]
        self.assertEqual(argument["desired_state"], "ARGUMENT")
        self.assertEqual(emphasis["desired_state"], "EMPHASIS")

    def test_tight_source_collapses_fake_states(self):
        result = plan(payload(importance=1.0, face_ratio=0.39))
        decision = result["decisions"][0]
        self.assertEqual(decision["available_states"], ["CONTEXT"])
        self.assertEqual(decision["state"], "CONTEXT")

    def test_moderate_keeps_argument_and_emphasis_as_distinct_working_states(self):
        result = plan(payload(importance=1.0, face_ratio=0.30))
        decision = result["decisions"][0]
        self.assertEqual(decision["available_states"], ["CONTEXT", "ARGUMENT", "EMPHASIS"])
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

    def test_long_eye_closure_and_pose_unsafe_are_rejected(self):
        result = plan(
            payload(
                candidates=[
                    {"id": "closed", "ms": 900, "word_boundary": True, "long_eye_closure": True},
                    {"id": "pose", "ms": 1000, "word_boundary": True, "pose_unsafe": True},
                    {"id": "safe", "ms": 1200, "word_boundary": True},
                ]
            )
        )
        self.assertEqual(result["decisions"][0]["start_ms"], 1200)

    def test_face_travel_degrades_close_state_before_it_can_clip(self):
        data = payload(importance=1.0, face_ratio=0.28)
        data["config"]["intensity"] = "dynamic"
        data["observations"] = observations(0.28)
        for row in data["observations"]:
            if row["t_ms"] == 750:
                row["face_cx"] = 0.28
            elif row["t_ms"] == 1250:
                row["face_cx"] = 0.72
        result = plan(data)
        decision = result["decisions"][0]
        self.assertNotEqual(decision["state"], "EMPHASIS")
        self.assertIn(decision["state"], {"CONTEXT", "ARGUMENT"})

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

    def test_build_peak_release_shapes_energy_without_pattern_loop(self):
        data = {
            "source": {"width": 2160, "height": 3840, "quality_cap": 1.60},
            "config": {"intensity": "dynamic", "window_ms": 800},
            "observations": observations(0.20),
            "semantic_events": [
                {
                    "id": "build",
                    "t_ms": 800,
                    "end_ms": 1300,
                    "importance": 1.0,
                    "direction": "build",
                    "boundary_candidates": [{"id": "b1", "ms": 800, "word_boundary": True}],
                },
                {
                    "id": "peak",
                    "t_ms": 1800,
                    "end_ms": 2300,
                    "importance": 1.0,
                    "direction": "peak",
                    "boundary_candidates": [{"id": "b2", "ms": 1800, "word_boundary": True}],
                },
                {
                    "id": "release",
                    "t_ms": 3100,
                    "end_ms": 3600,
                    "importance": 1.0,
                    "direction": "release",
                    "boundary_candidates": [{"id": "b3", "ms": 3100, "word_boundary": True}],
                },
            ],
        }
        result = plan(data)
        decisions = result["decisions"]
        self.assertEqual([d["direction"] for d in decisions], ["build", "peak", "release"])
        self.assertEqual([d["desired_state"] for d in decisions], ["ARGUMENT", "EMPHASIS", "CONTEXT"])
        self.assertEqual([d["state"] for d in decisions], ["ARGUMENT", "EMPHASIS", "CONTEXT"])

    def test_camera_cadence_is_only_a_soft_boundary_bonus(self):
        data = {
            "source": {"width": 2160, "height": 3840, "quality_cap": 1.60},
            "config": {"intensity": "moderate", "window_ms": 600},
            "observations": observations(0.20),
            "semantic_events": [
                {
                    "id": "first",
                    "t_ms": 500,
                    "end_ms": 900,
                    "importance": 0.70,
                    "direction": "build",
                    "boundary_candidates": [{"id": "b1", "ms": 500, "word_boundary": True}],
                },
                {
                    "id": "release",
                    "t_ms": 3000,
                    "end_ms": 3400,
                    "importance": 0.20,
                    "direction": "release",
                    "boundary_candidates": [
                        {"id": "near", "ms": 3000, "word_boundary": True},
                        {"id": "cadence", "ms": 3050, "word_boundary": True},
                    ],
                },
            ],
        }
        result = plan(data)
        second = result["decisions"][1]
        self.assertEqual(second["state"], "CONTEXT")
        self.assertGreaterEqual(second["cadence_bonus"], 0.0)
        self.assertEqual(result["config"]["preferred_change_ms"], 2500)

    def test_min_dwell_blocks_nervous_release_but_strong_peak_can_arrive_sooner(self):
        data = {
            "source": {"width": 2160, "height": 3840, "quality_cap": 1.60},
            "config": {"intensity": "dynamic", "window_ms": 600},
            "observations": observations(0.20),
            "semantic_events": [
                {
                    "id": "build",
                    "t_ms": 1000,
                    "end_ms": 1300,
                    "importance": 1.0,
                    "direction": "build",
                    "boundary_candidates": [{"id": "b1", "ms": 1000, "word_boundary": True}],
                },
                {
                    "id": "peak",
                    "t_ms": 1800,
                    "end_ms": 2100,
                    "importance": 1.0,
                    "direction": "peak",
                    "boundary_candidates": [{"id": "b2", "ms": 1800, "word_boundary": True}],
                },
                {
                    "id": "release-too-soon",
                    "t_ms": 2400,
                    "end_ms": 2700,
                    "importance": 1.0,
                    "direction": "release",
                    "boundary_candidates": [{"id": "b3", "ms": 2400, "word_boundary": True}],
                },
            ],
        }
        result = plan(data)
        self.assertEqual(result["decisions"][0]["state"], "ARGUMENT")
        self.assertEqual(result["decisions"][1]["state"], "EMPHASIS")
        self.assertEqual(result["decisions"][2]["status"], "KEEP")
        self.assertEqual(result["decisions"][2]["earliest_change_ms"], 3000)

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
