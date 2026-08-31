import unittest

from thz_planner.schema import CanonicalCrop, RenderPrimitive
from thz_render.contract import RenderKeyframe, RenderSegmentPlan
from thz_render.ffmpeg import (
    bind_sendcmd_file,
    compile_ffmpeg_segment,
    ffmpeg_program_sha256,
)


class FFmpegBackendTests(unittest.TestCase):
    def test_static_crop_needs_no_sendcmd(self):
        plan = RenderSegmentPlan(
            segment_id="hold",
            start_ms=0,
            end_ms=1000,
            primitive=RenderPrimitive.HOLD,
            keyframes=(RenderKeyframe(0, CanonicalCrop(0, 0, 1080, 1920)),),
        )
        program = compile_ffmpeg_segment(plan, source_w=1080, source_h=1920)
        self.assertIsNone(program.sendcmd_text)
        self.assertIn("crop@thz_hold=w=1080:h=1920:x=0:y=0:exact=1", program.filtergraph_template)
        self.assertIn("setsar=1", program.filtergraph_template)
        self.assertEqual((program.start_ms, program.end_ms), (0, 1000))

    def test_ramp_emits_exact_w_h_x_y_commands(self):
        plan = RenderSegmentPlan(
            segment_id="ramp-1",
            start_ms=1000,
            end_ms=2000,
            primitive=RenderPrimitive.LINEAR_RAMP,
            keyframes=(
                RenderKeyframe(1000, CanonicalCrop(0, 100, 1000, 1780)),
                RenderKeyframe(1500, CanonicalCrop(20, 110, 970, 1720)),
                RenderKeyframe(2000, CanonicalCrop(40, 120, 940, 1670)),
            ),
        )
        program = compile_ffmpeg_segment(plan, source_w=1080, source_h=1920)
        self.assertIn("0.500000 crop@thz_ramp_1 w 970;", program.sendcmd_text)
        self.assertIn("1.000000 crop@thz_ramp_1 h 1670;", program.sendcmd_text)
        self.assertIn("1.000000 crop@thz_ramp_1 x 40;", program.sendcmd_text)
        bound = bind_sendcmd_file(program, "/tmp/thz_cmd.txt")
        self.assertIn("sendcmd=f=/tmp/thz_cmd.txt", bound)
        self.assertIn("scale=1080:1920:flags=lanczos", bound)

    def test_renderer_program_hash_ignores_temp_file_binding(self):
        plan = RenderSegmentPlan(
            segment_id="ramp",
            start_ms=0,
            end_ms=1000,
            primitive=RenderPrimitive.LINEAR_RAMP,
            keyframes=(
                RenderKeyframe(0, CanonicalCrop(0, 0, 1080, 1920)),
                RenderKeyframe(1000, CanonicalCrop(40, 70, 1000, 1780)),
            ),
        )
        program = compile_ffmpeg_segment(plan, source_w=1080, source_h=1920)
        before = ffmpeg_program_sha256([program])
        bind_sendcmd_file(program, "/tmp/a.txt")
        bind_sendcmd_file(program, "/tmp/b.txt")
        after = ffmpeg_program_sha256([program])
        self.assertEqual(before, after)

        changed = compile_ffmpeg_segment(
            RenderSegmentPlan(
                segment_id="ramp",
                start_ms=0,
                end_ms=1000,
                primitive=RenderPrimitive.LINEAR_RAMP,
                keyframes=(
                    RenderKeyframe(0, CanonicalCrop(0, 0, 1080, 1920)),
                    RenderKeyframe(1000, CanonicalCrop(50, 70, 990, 1760)),
                ),
            ),
            source_w=1080,
            source_h=1920,
        )
        self.assertNotEqual(before, ffmpeg_program_sha256([changed]))

    def test_renderer_program_hash_changes_when_same_motion_moves_in_time(self):
        a = compile_ffmpeg_segment(
            RenderSegmentPlan(
                segment_id="ramp",
                start_ms=0,
                end_ms=1000,
                primitive=RenderPrimitive.LINEAR_RAMP,
                keyframes=(
                    RenderKeyframe(0, CanonicalCrop(0, 0, 1080, 1920)),
                    RenderKeyframe(1000, CanonicalCrop(40, 70, 1000, 1780)),
                ),
            ),
            source_w=1080,
            source_h=1920,
        )
        b = compile_ffmpeg_segment(
            RenderSegmentPlan(
                segment_id="ramp",
                start_ms=1000,
                end_ms=2000,
                primitive=RenderPrimitive.LINEAR_RAMP,
                keyframes=(
                    RenderKeyframe(1000, CanonicalCrop(0, 0, 1080, 1920)),
                    RenderKeyframe(2000, CanonicalCrop(40, 70, 1000, 1780)),
                ),
            ),
            source_w=1080,
            source_h=1920,
        )
        self.assertEqual(a.sendcmd_text, b.sendcmd_text)
        self.assertEqual(a.filtergraph_template, b.filtergraph_template)
        self.assertNotEqual(ffmpeg_program_sha256([a]), ffmpeg_program_sha256([b]))

    def test_backend_rejects_out_of_bounds_crop(self):
        plan = RenderSegmentPlan(
            segment_id="bad",
            start_ms=0,
            end_ms=1000,
            primitive=RenderPrimitive.HOLD,
            keyframes=(RenderKeyframe(0, CanonicalCrop(200, 0, 1000, 1920)),),
        )
        with self.assertRaises(ValueError):
            compile_ffmpeg_segment(plan, source_w=1080, source_h=1920)


if __name__ == "__main__":
    unittest.main()
