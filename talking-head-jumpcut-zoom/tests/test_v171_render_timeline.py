import unittest

from thz_planner.schema import (
    CanonicalCrop,
    FramingDecision,
    MotionIntent,
    RenderPrimitive,
    ShotState,
)
from thz_planner.timeline import ContentEdit, build_timeline_manifest
from thz_render import compile_ffmpeg_timeline


def hold(segment_id: str, start_ms: int, end_ms: int) -> FramingDecision:
    crop = CanonicalCrop(0, 0, 1080, 1920)
    return FramingDecision(
        segment_id=segment_id,
        start_ms=start_ms,
        end_ms=end_ms,
        state=ShotState.CONTEXT,
        motion_intent=MotionIntent.STATIC,
        primitive=RenderPrimitive.HOLD,
        crop_start=crop,
        crop_end=crop,
        anchor_policy="test",
        time_basis="output",
        derived={"motion_duration_ms": 0},
    )


class RenderTimelineTests(unittest.TestCase):
    def _manifest(self, second_src_start: int = 3000):
        return build_timeline_manifest(
            analysis_hash="a" * 64,
            config_hash="b" * 64,
            content_edits=[
                ContentEdit("keep_a", 1000, 2000, 0, 1000),
                ContentEdit("keep_b", second_src_start, second_src_start + 1000, 1000, 2000),
            ],
            framing_decisions=[
                hold("frame_a", 0, 1000),
                hold("frame_b", 1000, 2000),
            ],
            source_type="live",
        )

    def test_timeline_program_maps_output_segments_to_kept_source_intervals(self):
        program = compile_ffmpeg_timeline(
            self._manifest(),
            fps=30.0,
            source_w=1080,
            source_h=1920,
        )
        self.assertEqual(len(program.segments), 2)
        self.assertEqual(
            (program.segments[0].source_start_ms, program.segments[0].source_end_ms),
            (1000, 2000),
        )
        self.assertEqual(
            (program.segments[1].source_start_ms, program.segments[1].source_end_ms),
            (3000, 4000),
        )
        self.assertEqual(len(program.renderer_program_sha256), 64)

    def test_renderer_hash_changes_when_jumpcut_source_mapping_changes(self):
        a = compile_ffmpeg_timeline(
            self._manifest(3000),
            fps=30.0,
            source_w=1080,
            source_h=1920,
        )
        b = compile_ffmpeg_timeline(
            self._manifest(5000),
            fps=30.0,
            source_w=1080,
            source_h=1920,
        )
        self.assertNotEqual(a.renderer_program_sha256, b.renderer_program_sha256)
        self.assertNotEqual(a.segments[1].source_start_ms, b.segments[1].source_start_ms)


if __name__ == "__main__":
    unittest.main()
