import unittest

from thz_planner.static_policy import (
    StarvationStep,
    VisualActivity,
    assess_static_stretch,
    validate_starvation_ladder,
)
from thz_render.ai_fx import default_ai_deplastic_drift, validate_ai_deplastic_drift


class StaticStretchPolicyTests(unittest.TestCase):
    def test_discrete_event_resets_timer(self):
        result = assess_static_stretch(
            pace="neutral",
            elapsed_ms=9000,
            activity=VisualActivity.DISCRETE_EVENT,
        )
        self.assertTrue(result.resets_timer)
        self.assertEqual(result.status, "pass")

    def test_ambient_drift_does_not_extend_cap(self):
        result = assess_static_stretch(
            pace="calm",
            elapsed_ms=7000,
            activity=VisualActivity.AMBIENT_DRIFT,
            verified_scale_rate_per_s=0.005,
        )
        self.assertFalse(result.motion_credit)
        self.assertEqual(result.effective_cap_ms, 6500)
        self.assertEqual(result.status, "starvation_required")

    def test_semantic_push_gets_extension_only_above_verified_rate(self):
        low = assess_static_stretch(
            pace="neutral",
            elapsed_ms=6500,
            activity=VisualActivity.SEMANTIC_PUSH,
            verified_scale_rate_per_s=0.005,
        )
        credited = assess_static_stretch(
            pace="neutral",
            elapsed_ms=6500,
            activity=VisualActivity.SEMANTIC_PUSH,
            verified_scale_rate_per_s=0.008,
        )
        self.assertEqual(low.status, "starvation_required")
        self.assertFalse(low.motion_credit)
        self.assertEqual(credited.status, "pass")
        self.assertTrue(credited.motion_credit)
        self.assertEqual(credited.effective_cap_ms, 8000)

    def test_ai_deplastic_drift_never_earns_static_credit(self):
        result = assess_static_stretch(
            pace="neutral",
            elapsed_ms=6000,
            activity=VisualActivity.AI_DEPLASTIC_DRIFT,
            verified_scale_rate_per_s=0.02,
        )
        self.assertFalse(result.motion_credit)
        self.assertEqual(result.status, "starvation_required")

    def test_r1_r5_contract_requires_exact_migrated_order(self):
        steps = tuple(
            StarvationStep(f"R{i}", f"legacy_action_{i}", f"legacy_r{i}")
            for i in range(1, 6)
        )
        validate_starvation_ladder(steps)
        with self.assertRaises(ValueError):
            validate_starvation_ladder(steps[:-1])


class AIDeplasticTests(unittest.TestCase):
    def test_default_ai_drift_is_non_semantic(self):
        drift = default_ai_deplastic_drift()
        validate_ai_deplastic_drift(drift)
        self.assertEqual((drift.start_scale, drift.end_scale), (1.0, 1.02))
        self.assertFalse(drift.counts_as_semantic_motion)
        self.assertFalse(drift.counts_as_static_extension)


if __name__ == "__main__":
    unittest.main()
