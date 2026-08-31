import unittest

from thz_critic import CheckRegistry, CheckResult
from thz_planner import plan_geometry_core, render_geometry_result
from thz_planner.schema import FrameObservation, QualityMetrics, ShotState, stable_candidate_sort


def observations(face_ratio=0.30, *, blocked_bucket=False):
    rows = []
    for t in range(0, 2000, 250):
        blocked = blocked_bucket and 500 <= t < 1000
        rows.append(
            FrameObservation(
                t_ms=t,
                face_ratio=face_ratio,
                face_cx=0.50,
                face_cy=0.34,
                hair_top=0.15,
                bottom_keep_y=0.72,
                gesture_hard_block=blocked,
            )
        )
    return rows


class PlannerCoreTests(unittest.TestCase):
    def test_same_input_is_byte_stable(self):
        kwargs = dict(
            observations=observations(),
            quality=QualityMetrics(1080, 1920, sharpness=0.8, noise=0.1, compression=0.1),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        a = render_geometry_result(plan_geometry_core(**kwargs))
        b = render_geometry_result(plan_geometry_core(**kwargs))
        self.assertEqual(a, b)

    def test_redundant_argument_collapses_to_two_states(self):
        result = plan_geometry_core(
            observations=observations(0.30),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        states = [s.state for s in result["windows"][0]["distinct_states"]]
        self.assertEqual(states, [ShotState.CONTEXT, ShotState.EMPHASIS])

    def test_tight_source_can_collapse_to_one_state(self):
        result = plan_geometry_core(
            observations=observations(0.41),
            quality=QualityMetrics(1080, 1920),
            intensity="calm",
            pace="calm",
            window_ms=500,
        )
        states = result["windows"][0]["distinct_states"]
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].state, ShotState.EMPHASIS)

    def test_temporal_hard_block_only_poisoned_window(self):
        result = plan_geometry_core(
            observations=observations(0.30, blocked_bucket=True),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        self.assertTrue(result["windows"][0]["distinct_states"])
        self.assertFalse(result["windows"][1]["distinct_states"])
        self.assertTrue(result["windows"][2]["distinct_states"])

    def test_deterministic_candidate_tie_break(self):
        items = [
            {"id": "b", "score": 0.8, "semantic_fit": 0.7, "ms": 1000},
            {"id": "a", "score": 0.8, "semantic_fit": 0.7, "ms": 1000},
            {"id": "c", "score": 0.8, "semantic_fit": 0.8, "ms": 1200},
        ]
        ordered = stable_candidate_sort(items)
        self.assertEqual([x["id"] for x in ordered], ["c", "a", "b"])


class CriticRegistryTests(unittest.TestCase):
    def test_coverage_and_verdict_are_separate(self):
        registry = CheckRegistry()
        expected = registry.resolve(profile="live")
        results = [CheckResult(spec.check_id, "pass") for spec in expected]
        summary = registry.summarize(results, profile="live")
        self.assertEqual(summary["coverage"], 1.0)
        self.assertEqual(summary["pass_rate"], 1.0)
        self.assertEqual(summary["verdict"], "GO")

        failed = list(results)
        failed[0] = CheckResult(failed[0].check_id, "fail")
        summary = registry.summarize(failed, profile="live")
        self.assertEqual(summary["coverage"], 1.0)
        self.assertLess(summary["pass_rate"], 1.0)
        self.assertEqual(summary["verdict"], "NO_GO")


if __name__ == "__main__":
    unittest.main()
