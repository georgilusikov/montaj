import unittest

from thz_planner.assembler import materialize_framing_decision
from thz_planner.decision import plan_transition_intent
from thz_planner.planner import plan_geometry_core
from thz_planner.schema import FrameObservation, QualityMetrics, ShotState
from thz_planner.when_solver import BoundaryCandidate
from thz_planner.window_queries import state_is_feasible


def observations():
    rows = []
    for t in range(0, 3000, 250):
        rows.append(
            FrameObservation(
                t_ms=t,
                face_ratio=0.30,
                face_cx=0.50,
                face_cy=0.34,
                hair_top=0.15,
                bottom_keep_y=0.72,
                gesture_hard_block=1500 <= t < 2000,
            )
        )
    return rows


class AssemblerTests(unittest.TestCase):
    def test_nominal_buckets_cover_time_between_probe_samples(self):
        geometry = plan_geometry_core(
            observations=observations(),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        self.assertTrue(state_is_feasible(geometry, ShotState.EMPHASIS, 400))
        self.assertFalse(state_is_feasible(geometry, ShotState.EMPHASIS, 1750))

    def test_framing_is_clipped_before_future_infeasible_window(self):
        rows = observations()
        quality = QualityMetrics(1080, 1920)
        geometry = plan_geometry_core(
            observations=rows,
            quality=quality,
            intensity="calm",
            pace="calm",
            window_ms=500,
        )
        transition = plan_transition_intent(
            geometry_result=geometry,
            semantic_at_ms=1000,
            current_state=ShotState.ARGUMENT,
            current_scale=1.08,
            semantic_weight=1.0,
            salience=1.0,
            prosody=1.0,
            theme_tag="warning",
            boundary_candidates=[BoundaryCandidate("safe", 1250, semantic_fit=1.0, word_boundary=True)],
            profile="live",
            pace="calm",
        )
        self.assertEqual(transition["status"], "PLANNED")
        framing = materialize_framing_decision(
            transition=transition,
            geometry_result=geometry,
            observations=rows,
            quality=quality,
            segment_id="seg_001",
            requested_end_ms=2500,
        )
        self.assertEqual(framing.end_ms, 1499)
        self.assertTrue(framing.derived["clipped_to_feasibility"])
        self.assertLessEqual(framing.crop_start.x + framing.crop_start.w, quality.width)
        self.assertLessEqual(framing.crop_end.y + framing.crop_end.h, quality.height)


if __name__ == "__main__":
    unittest.main()
