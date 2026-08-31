import unittest

from thz_planner import (
    canonical_crop_at,
    canonical_crop_pair,
    feasible_ranges,
    plan_geometry_core,
    state_is_feasible,
)
from thz_planner.schema import FrameObservation, QualityMetrics, ShotState


class CanonicalFramingTests(unittest.TestCase):
    def test_crop_is_even_and_inside_source(self):
        metrics = QualityMetrics(1080, 1920)
        obs = FrameObservation(
            t_ms=0,
            face_ratio=0.30,
            face_cx=0.62,
            face_cy=0.34,
            hair_top=0.14,
            bottom_keep_y=0.72,
        )
        crop = canonical_crop_at(
            observation=obs,
            metrics=metrics,
            scale=1.16,
            segment_hair_top=0.14,
        )
        self.assertEqual(crop.x % 2, 0)
        self.assertEqual(crop.y % 2, 0)
        self.assertEqual(crop.w % 2, 0)
        self.assertEqual(crop.h % 2, 0)
        self.assertGreaterEqual(crop.x, 0)
        self.assertGreaterEqual(crop.y, 0)
        self.assertLessEqual(crop.x + crop.w, metrics.width)
        self.assertLessEqual(crop.y + crop.h, metrics.height)

    def test_scale_below_one_is_rejected(self):
        obs = FrameObservation(0, 0.3, 0.5, 0.34, 0.15, 0.72)
        with self.assertRaises(ValueError):
            canonical_crop_at(
                observation=obs,
                metrics=QualityMetrics(1080, 1920),
                scale=0.99,
                segment_hair_top=0.15,
            )

    def test_pair_uses_segment_wide_hair_top(self):
        metrics = QualityMetrics(1080, 1920)
        rows = [
            FrameObservation(0, 0.30, 0.48, 0.34, 0.16, 0.72),
            FrameObservation(500, 0.30, 0.52, 0.34, 0.12, 0.72),
        ]
        start, end = canonical_crop_pair(
            observations=rows,
            metrics=metrics,
            start_scale=1.08,
            end_scale=1.12,
        )
        self.assertGreaterEqual(start.y, 0)
        self.assertGreaterEqual(end.y, 0)
        # Lower hair_top in the second observation constrains both endpoints.
        local_only = canonical_crop_at(
            observation=rows[0],
            metrics=metrics,
            scale=1.08,
            segment_hair_top=rows[0].hair_top,
        )
        self.assertLessEqual(start.y, local_only.y)


class TemporalQueryTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for t in range(0, 2000, 250):
            rows.append(
                FrameObservation(
                    t_ms=t,
                    face_ratio=0.30,
                    face_cx=0.50,
                    face_cy=0.34,
                    hair_top=0.15,
                    bottom_keep_y=0.72,
                    gesture_hard_block=500 <= t < 1000,
                )
            )
        return rows

    def test_state_query_respects_temporal_block(self):
        result = plan_geometry_core(
            observations=self._rows(),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        self.assertTrue(state_is_feasible(result, ShotState.EMPHASIS, 250))
        self.assertFalse(state_is_feasible(result, ShotState.EMPHASIS, 750))
        self.assertTrue(state_is_feasible(result, ShotState.EMPHASIS, 1250))

    def test_feasible_ranges_do_not_bridge_blocked_window(self):
        result = plan_geometry_core(
            observations=self._rows(),
            quality=QualityMetrics(1080, 1920),
            intensity="moderate",
            pace="neutral",
            window_ms=500,
        )
        ranges = feasible_ranges(result, ShotState.EMPHASIS)
        self.assertGreaterEqual(len(ranges), 2)
        self.assertLess(ranges[0][1], ranges[1][0])


if __name__ == "__main__":
    unittest.main()
