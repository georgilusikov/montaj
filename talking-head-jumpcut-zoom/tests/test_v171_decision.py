import unittest

from thz_planner.decision import plan_transition_intent
from thz_planner.motion import plan_motion
from thz_planner.patterns import pattern_candidates
from thz_planner.planner import plan_geometry_core
from thz_planner.schema import FrameObservation, QualityMetrics, RenderPrimitive, ShotState
from thz_planner.when_solver import BoundaryCandidate, solve_ai_when, solve_live_when
from thz_planner.why import resolve_why


def rows(*, blocked=False, duration=3000):
    out = []
    for t in range(0, duration, 250):
        out.append(
            FrameObservation(
                t_ms=t,
                face_ratio=0.30,
                face_cx=0.50,
                face_cy=0.34,
                hair_top=0.15,
                bottom_keep_y=0.72,
                gesture_hard_block=blocked and 500 <= t < 1000,
            )
        )
    return out


class WhyTests(unittest.TestCase):
    def test_gaze_cannot_create_emphasis_in_why(self):
        result = resolve_why(semantic_weight=0.0, salience=0.0, prosody=0.0, narrative=0.0)
        self.assertEqual(result["desired_state"], ShotState.CONTEXT)

    def test_strong_semantics_select_emphasis(self):
        result = resolve_why(semantic_weight=1.0, salience=1.0, prosody=1.0, narrative=1.0)
        self.assertEqual(result["desired_state"], ShotState.EMPHASIS)


class PatternTests(unittest.TestCase):
    def test_patterns_degrade_to_available_states(self):
        candidates = pattern_candidates(
            theme_tag="warning",
            available_states={ShotState.CONTEXT, ShotState.EMPHASIS},
            semantic_fit=0.9,
            prosody_fit=0.7,
        )
        ladder = next(x for x in candidates if x["pattern_id"] == "ladder")
        self.assertTrue(ladder["degraded"])
        self.assertEqual(ladder["usable_states"], (ShotState.CONTEXT, ShotState.EMPHASIS))


class WhenTests(unittest.TestCase):
    def test_live_blink_is_hard_mask(self):
        selected = solve_live_when([
            BoundaryCandidate("blocked", 1000, semantic_fit=1.0, word_boundary=True, blink_block=True),
            BoundaryCandidate("safe", 1100, semantic_fit=0.6, word_boundary=True),
        ])
        self.assertEqual(selected["id"], "safe")

    def test_head_return_is_bonus_not_requirement(self):
        selected = solve_live_when([
            BoundaryCandidate("return", 1100, semantic_fit=0.5, head_return=True),
            BoundaryCandidate("semantic", 1000, semantic_fit=1.0, word_boundary=True),
        ])
        self.assertEqual(selected["id"], "semantic")

    def test_ai_requires_artifact_peak_and_cadence(self):
        selected = solve_ai_when([
            BoundaryCandidate("too_early", 1500, semantic_fit=1.0, artifact_peak=True),
            BoundaryCandidate("no_artifact", 2500, semantic_fit=1.0, phoneme_boundary=True),
            BoundaryCandidate("valid", 2600, semantic_fit=0.7, artifact_peak=True, phoneme_boundary=True),
        ], segment_start_ms=0)
        self.assertEqual(selected["id"], "valid")


class MotionTests(unittest.TestCase):
    def test_small_strong_change_becomes_ramp_not_fake_step(self):
        motion = plan_motion(
            current_state=ShotState.ARGUMENT,
            desired_state=ShotState.EMPHASIS,
            current_scale=1.08,
            target_scale=1.12,
            semantic_weight=0.95,
            pace="neutral",
        )
        self.assertEqual(motion.primitive, RenderPrimitive.LINEAR_RAMP)
        self.assertAlmostEqual(motion.end_scale, 1.12)


class DecisionIntegrationTests(unittest.TestCase):
    def test_when_filters_candidate_by_temporal_feasibility(self):
        geometry = plan_geometry_core(
            observations=rows(blocked=True),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        result = plan_transition_intent(
            geometry_result=geometry,
            semantic_at_ms=250,
            current_state=ShotState.CONTEXT,
            current_scale=1.0,
            semantic_weight=1.0,
            salience=1.0,
            prosody=1.0,
            theme_tag="warning",
            boundary_candidates=[
                BoundaryCandidate("blocked_window", 750, semantic_fit=1.0, word_boundary=True),
                BoundaryCandidate("safe_window", 1250, semantic_fit=0.8, word_boundary=True),
            ],
            profile="live",
            pace="neutral",
        )
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["when"]["id"], "safe_window")


if __name__ == "__main__":
    unittest.main()
