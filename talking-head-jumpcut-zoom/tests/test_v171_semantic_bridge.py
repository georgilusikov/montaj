import unittest

from thz_planner.planner import plan_geometry_core
from thz_planner.schema import FrameObservation, QualityMetrics, ShotState
from thz_planner.semantic_bridge import plan_transition_from_semantic_context
from thz_planner.when_solver import BoundaryCandidate
from thz_semantics import (
    ActAnnotation,
    ProsodySample,
    detect_breath_intervals,
    detect_prosody_peaks,
    detect_salience,
    distance_to_breath_ms,
    semantic_context_at,
)


def geometry_rows():
    return [
        FrameObservation(t, 0.30, 0.50, 0.34, 0.15, 0.72)
        for t in range(0, 3000, 250)
    ]


class SemanticBridgeTests(unittest.TestCase):
    def test_prosody_and_breath_are_facts(self):
        samples = [
            ProsodySample(0, 0.0, 0.0),
            ProsodySample(500, 1.8, 1.6),
            ProsodySample(1000, -0.8, -1.4),
        ]
        peaks = detect_prosody_peaks(samples)
        breaths = detect_breath_intervals(samples)
        self.assertEqual(len(peaks), 1)
        self.assertEqual(len(breaths), 1)
        self.assertEqual(distance_to_breath_ms(1000, breaths), 0)

    def test_frozen_semantics_drive_why_without_gaze(self):
        hits = detect_salience((
            {"start_ms": 400, "end_ms": 800, "text": "Главная ошибка — никогда так не делать."},
        ))
        peaks = detect_prosody_peaks([
            ProsodySample(500, 2.5, 2.0),
        ])
        acts = (
            ActAnnotation("act_01", 0, 2000, 1.0, (("warning", 0.9),)),
        )
        context = semantic_context_at(500, salience_hits=hits, prosody_peaks=peaks, acts=acts)
        self.assertEqual(context["theme_tag"], "warning")
        self.assertGreater(context["prosody"], 0.8)

        geometry = plan_geometry_core(
            observations=geometry_rows(),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        result = plan_transition_from_semantic_context(
            context,
            geometry_result=geometry,
            semantic_at_ms=500,
            current_state=ShotState.CONTEXT,
            current_scale=1.0,
            boundary_candidates=[
                BoundaryCandidate("boundary", 600, semantic_fit=1.0, word_boundary=True),
            ],
            profile="live",
            pace="neutral",
        )
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["desired_state"], ShotState.EMPHASIS)

    def test_later_act_start_emits_reset_context(self):
        acts = (
            ActAnnotation("a", 0, 1000, 0.9, (("story", 0.8),)),
            ActAnnotation("b", 1000, 2000, 0.9, (("warning", 0.8),)),
        )
        context = semantic_context_at(1100, acts=acts)
        self.assertTrue(context["act_reset"])


if __name__ == "__main__":
    unittest.main()
