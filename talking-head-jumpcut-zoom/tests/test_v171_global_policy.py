import unittest

from thz_planner.global_policy import (
    home_return_report,
    outro_breath_policy,
    state_balance_report,
)
from thz_planner.schema import (
    CanonicalCrop,
    FramingDecision,
    MotionIntent,
    RenderPrimitive,
    ShotState,
)


def framing(segment_id, start, end, state, *, coverage=False):
    crop = CanonicalCrop(0, 0, 1080, 1920)
    return FramingDecision(
        segment_id=segment_id,
        start_ms=start,
        end_ms=end,
        state=state,
        motion_intent=MotionIntent.STATIC,
        primitive=RenderPrimitive.HOLD,
        crop_start=crop,
        crop_end=crop,
        anchor_policy="test",
        time_basis="output",
        derived={"motion_duration_ms": 0, "coverage_generated": coverage},
    )


class GlobalPolicyTests(unittest.TestCase):
    def test_home_return_flags_long_unbroken_non_home_run(self):
        rows = [framing("arg", 0, 13000, ShotState.ARGUMENT)]
        violations = home_return_report(rows)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].duration_ms, 13000)

    def test_explicit_source_base_is_home_even_for_naturally_tight_source(self):
        rows = [
            framing("a", 0, 7000, ShotState.EMPHASIS),
            framing("base", 7000, 8000, ShotState.EMPHASIS, coverage=True),
            framing("b", 8000, 15000, ShotState.ARGUMENT),
        ]
        self.assertFalse(home_return_report(rows))

    def test_state_balance_is_information_not_verdict(self):
        report = state_balance_report(
            [
                framing("c", 0, 2000, ShotState.CONTEXT),
                framing("a", 2000, 8000, ShotState.ARGUMENT),
                framing("e", 8000, 10000, ShotState.EMPHASIS),
            ],
            pace="neutral",
        )
        self.assertAlmostEqual(report.context_share, 0.20)
        self.assertAlmostEqual(report.argument_share, 0.60)
        self.assertIn("context_share_below_prior", report.info_flags)
        self.assertIn("argument_share_above_prior", report.info_flags)

    def test_strong_final_can_use_one_second_outro_breath(self):
        strong = outro_breath_policy(pace="neutral", final_semantic_weight=0.9, actual_ms=1000)
        normal = outro_breath_policy(pace="neutral", final_semantic_weight=0.5, actual_ms=1000)
        self.assertEqual(strong.required_min_ms, 1000)
        self.assertEqual(strong.status, "pass")
        self.assertEqual(normal.required_min_ms, 2000)
        self.assertEqual(normal.status, "warn")


if __name__ == "__main__":
    unittest.main()
