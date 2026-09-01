import unittest

from thz_planner.coverage import (
    output_coverage_gaps,
    source_coverage_gaps,
    synthesize_source_base_coverage,
)
from thz_planner.schema import (
    CanonicalCrop,
    FrameObservation,
    FramingDecision,
    MotionIntent,
    QualityMetrics,
    RenderPrimitive,
    ShotState,
)
from thz_planner.timeline import ContentEdit, build_timeline_manifest
from thz_planner.validator import validate_manifest_pre_render


class CoverageTests(unittest.TestCase):
    def _semantic(self):
        crop = CanonicalCrop(40, 70, 1000, 1780)
        return FramingDecision(
            segment_id="semantic",
            start_ms=600,
            end_ms=1400,
            state=ShotState.EMPHASIS,
            motion_intent=MotionIntent.SEMANTIC_PUSH,
            primitive=RenderPrimitive.STEP,
            crop_start=crop,
            crop_end=crop,
            anchor_policy="tracked_face_segment_headroom",
            time_basis="source",
            why={"reason": "semantic_emphasis"},
            derived={"motion_duration_ms": 0},
        )

    def _rows(self):
        return [
            FrameObservation(t, 0.30, 0.50, 0.34, 0.15, 0.72)
            for t in range(0, 2001, 250)
        ]

    def test_sparse_semantic_framing_has_two_source_gaps(self):
        content = [ContentEdit("keep", 0, 2000, 0, 2000)]
        gaps = source_coverage_gaps(content, [self._semantic()])
        self.assertEqual([(g.start_ms, g.end_ms) for g in gaps], [(0, 600), (1400, 2000)])

    def test_coverage_synthesis_fills_kept_timeline_with_source_base(self):
        content = [ContentEdit("keep", 0, 2000, 0, 2000)]
        framing = synthesize_source_base_coverage(
            content_edits=content,
            framing_decisions=[self._semantic()],
            observations=self._rows(),
            quality=QualityMetrics(1080, 1920),
        )
        self.assertFalse(source_coverage_gaps(content, framing))
        generated = [item for item in framing if item.derived.get("coverage_generated")]
        self.assertEqual(len(generated), 2)
        for item in generated:
            self.assertEqual(item.crop_start, CanonicalCrop(0, 0, 1080, 1920))
            self.assertEqual(item.crop_start, item.crop_end)
            self.assertFalse(item.why["semantic_trigger"])
            self.assertEqual(item.derived["motion_end_scale"], 1.0)

        manifest = build_timeline_manifest(
            analysis_hash="a",
            config_hash="c",
            content_edits=content,
            framing_decisions=framing,
            source_type="live",
        )
        self.assertFalse(output_coverage_gaps(manifest))
        summary = validate_manifest_pre_render(
            manifest,
            quality=QualityMetrics(1080, 1920),
        )
        self.assertEqual(summary["coverage_gap_count"], 0)
        self.assertEqual(summary["framing_coverage"], 1.0)

    def test_sparse_renderer_manifest_is_rejected(self):
        manifest = build_timeline_manifest(
            analysis_hash="a",
            config_hash="c",
            content_edits=[ContentEdit("keep", 0, 2000, 0, 2000)],
            framing_decisions=[self._semantic()],
            source_type="live",
        )
        with self.assertRaisesRegex(ValueError, "coverage gaps"):
            validate_manifest_pre_render(
                manifest,
                quality=QualityMetrics(1080, 1920),
            )


if __name__ == "__main__":
    unittest.main()
