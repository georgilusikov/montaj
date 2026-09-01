import unittest

from thz_planner.schema import CanonicalCrop, FramingDecision, MotionIntent, RenderPrimitive, ShotState
from thz_render import compile_framing_keyframes, compile_render_plan


class RenderContractTests(unittest.TestCase):
    def _decision(self, primitive=RenderPrimitive.LINEAR_RAMP):
        return FramingDecision(
            segment_id="seg",
            start_ms=1000,
            end_ms=3000,
            state=ShotState.EMPHASIS,
            motion_intent=MotionIntent.SEMANTIC_PUSH,
            primitive=primitive,
            crop_start=CanonicalCrop(0, 100, 1000, 1780),
            crop_end=CanonicalCrop(40, 120, 940, 1670),
            anchor_policy="tracked_face_segment_headroom",
            time_basis="output",
            derived={"motion_duration_ms": 1000},
        )

    def test_ramp_preserves_exact_endpoints(self):
        decision = self._decision()
        frames = compile_framing_keyframes(decision, fps=30)
        self.assertEqual(frames[0].crop, decision.crop_start)
        self.assertEqual(frames[-1].crop, decision.crop_end)
        self.assertEqual(frames[0].t_ms, 1000)
        self.assertEqual(frames[-1].t_ms, 2000)

    def test_interpolated_crops_are_even(self):
        frames = compile_framing_keyframes(self._decision(), fps=30)
        for frame in frames:
            self.assertFalse(any(v % 2 for v in (frame.crop.x, frame.crop.y, frame.crop.w, frame.crop.h)))

    def test_step_is_resolved_to_new_crop_at_boundary(self):
        decision = self._decision(RenderPrimitive.STEP)
        frames = compile_framing_keyframes(decision, fps=30)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].crop, decision.crop_end)

    def test_renderer_rejects_source_time_decision(self):
        decision = self._decision()
        decision = FramingDecision(**{**decision.__dict__, "time_basis": "source"})
        with self.assertRaises(ValueError):
            compile_framing_keyframes(decision, fps=30)

    def test_render_plan_is_stably_sorted(self):
        a = self._decision()
        b = FramingDecision(**{**a.__dict__, "segment_id": "a", "start_ms": 500, "end_ms": 900})
        manifest = {"framing_decisions": (a, b)}
        plan = compile_render_plan(manifest, fps=30)
        self.assertEqual([x.segment_id for x in plan], ["a", "seg"])


if __name__ == "__main__":
    unittest.main()
