import unittest

from thz_critic.framing import (
    RenderedCompositionSample,
    composition_safe_report,
    motion_fidelity_report,
)


class IndependentFramingCriticTests(unittest.TestCase):
    def _sample(self, *, t=0, top=0.06, crop=(0, 0, 1080, 1920)):
        return RenderedCompositionSample(
            t_ms=t,
            top_margin=top,
            bottom_margin=0.05,
            left_margin=0.10,
            right_margin=0.10,
            caption_overlap=0.0,
            crop_x=crop[0],
            crop_y=crop[1],
            crop_w=crop[2],
            crop_h=crop[3],
        )

    def test_composition_failure_is_measured_from_render(self):
        report = composition_safe_report([
            self._sample(t=0, top=0.06),
            self._sample(t=500, top=0.03),
        ])
        self.assertEqual(report["status"], "fail")
        self.assertIn("top_margin", report["failures"])

    def test_motion_fidelity_uses_measured_crop_endpoints(self):
        report = motion_fidelity_report(
            [
                self._sample(t=0, crop=(10, 20, 1000, 1800)),
                self._sample(t=500, crop=(20, 30, 960, 1720)),
            ],
            expected_start_crop=(10, 20, 1000, 1800),
            expected_end_crop=(20, 30, 960, 1720),
            tolerance_px=2,
        )
        self.assertEqual(report["status"], "pass")

    def test_motion_fidelity_fails_large_renderer_deviation(self):
        report = motion_fidelity_report(
            [
                self._sample(t=0, crop=(10, 20, 1000, 1800)),
                self._sample(t=500, crop=(30, 30, 960, 1720)),
            ],
            expected_start_crop=(10, 20, 1000, 1800),
            expected_end_crop=(20, 30, 960, 1720),
            tolerance_px=4,
        )
        self.assertEqual(report["status"], "fail")


if __name__ == "__main__":
    unittest.main()
