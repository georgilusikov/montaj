import unittest

from thz_planner.schema import (
    CanonicalCrop,
    FramingDecision,
    MotionIntent,
    QualityMetrics,
    RenderPrimitive,
    ShotState,
    canonical_json,
)
from thz_planner.timeline import ContentEdit, build_timeline_manifest
from thz_planner.validator import validate_manifest_pre_render


class TimelineContractTests(unittest.TestCase):
    def _framing(self):
        crop = CanonicalCrop(0, 0, 1080, 1920)
        return FramingDecision(
            segment_id="frame_01",
            start_ms=1200,
            end_ms=1500,
            state=ShotState.CONTEXT,
            motion_intent=MotionIntent.STATIC,
            primitive=RenderPrimitive.HOLD,
            crop_start=crop,
            crop_end=crop,
            anchor_policy="tracked_face_segment_headroom",
            derived={"motion_duration_ms": 0},
        )

    def _full_framing(self):
        crop = CanonicalCrop(0, 0, 1080, 1920)
        return FramingDecision(
            segment_id="frame_full",
            start_ms=1000,
            end_ms=2000,
            state=ShotState.CONTEXT,
            motion_intent=MotionIntent.STATIC,
            primitive=RenderPrimitive.HOLD,
            crop_start=crop,
            crop_end=crop,
            anchor_policy="source_base_explicit_coverage",
            derived={"motion_duration_ms": 0, "coverage_generated": True},
        )

    def test_source_framing_maps_to_output_time(self):
        manifest = build_timeline_manifest(
            analysis_hash="a",
            config_hash="c",
            content_edits=[ContentEdit("content_01", 1000, 2000, 0, 1000)],
            framing_decisions=[self._framing()],
            source_type="live",
        )
        framing = manifest["framing_decisions"][0]
        self.assertEqual(framing.time_basis, "output")
        self.assertEqual((framing.start_ms, framing.end_ms), (200, 500))

    def test_framing_cannot_cross_removed_content(self):
        framing = self._framing()
        with self.assertRaises(ValueError):
            build_timeline_manifest(
                analysis_hash="a",
                config_hash="c",
                content_edits=[
                    ContentEdit("a", 1000, 1300, 0, 300),
                    ContentEdit("b", 1400, 2000, 300, 900),
                ],
                framing_decisions=[framing],
                source_type="live",
            )

    def test_output_framing_cannot_cross_jumpcut_boundary(self):
        crop = CanonicalCrop(0, 0, 1080, 1920)
        crossing = FramingDecision(
            segment_id="crossing",
            start_ms=400,
            end_ms=600,
            state=ShotState.CONTEXT,
            motion_intent=MotionIntent.STATIC,
            primitive=RenderPrimitive.HOLD,
            crop_start=crop,
            crop_end=crop,
            anchor_policy="test",
            time_basis="output",
            derived={"motion_duration_ms": 0},
        )
        with self.assertRaisesRegex(ValueError, "output framing"):
            build_timeline_manifest(
                analysis_hash="a",
                config_hash="c",
                content_edits=[
                    ContentEdit("a", 1000, 1500, 0, 500),
                    ContentEdit("b", 2000, 2500, 500, 1000),
                ],
                framing_decisions=[crossing],
                source_type="live",
            )

    def test_manifest_is_byte_stable_and_pre_render_valid(self):
        kwargs = dict(
            analysis_hash="a",
            config_hash="c",
            content_edits=[ContentEdit("content_01", 1000, 2000, 0, 1000)],
            framing_decisions=[self._full_framing()],
            source_type="live",
        )
        a = build_timeline_manifest(**kwargs)
        b = build_timeline_manifest(**kwargs)
        self.assertEqual(canonical_json(a), canonical_json(b))
        summary = validate_manifest_pre_render(a, quality=QualityMetrics(1080, 1920))
        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["coverage_gap_count"], 0)

    def test_sparse_manifest_can_be_inspected_but_not_render_validated(self):
        manifest = build_timeline_manifest(
            analysis_hash="a",
            config_hash="c",
            content_edits=[ContentEdit("content_01", 1000, 2000, 0, 1000)],
            framing_decisions=[self._framing()],
            source_type="live",
        )
        with self.assertRaisesRegex(ValueError, "coverage gaps"):
            validate_manifest_pre_render(manifest, quality=QualityMetrics(1080, 1920))
        summary = validate_manifest_pre_render(
            manifest,
            quality=QualityMetrics(1080, 1920),
            require_full_coverage=False,
        )
        self.assertGreater(summary["coverage_gap_count"], 0)

    def test_non_1_to_1_content_mapping_is_rejected(self):
        with self.assertRaises(ValueError):
            build_timeline_manifest(
                analysis_hash="a",
                config_hash="c",
                content_edits=[ContentEdit("bad", 0, 1000, 0, 900)],
                framing_decisions=[],
                source_type="live",
            )


if __name__ == "__main__":
    unittest.main()
