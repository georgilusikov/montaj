import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from post_render_qc import verify  # noqa: E402


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for render canary")
class PostRenderQCTests(unittest.TestCase):
    def test_accepts_expected_crop_and_rejects_noop_render(self):
        with tempfile.TemporaryDirectory(prefix="montaj_postqc_test_") as tmp_dir:
            tmp = Path(tmp_dir)
            dense = tmp / "dense.mp4"
            correct = tmp / "correct.mp4"
            noop = tmp / "noop.mp4"

            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi",
                    "-i", "testsrc2=size=216x384:rate=30:duration=1.5",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(dense),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-y",
                    "-i", str(dense),
                    "-vf", "crop=180:320:18:32:exact=1,scale=216:384:flags=lanczos",
                    "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
                    str(correct),
                ],
                check=True,
            )
            shutil.copyfile(dense, noop)

            plan = {
                "source": {"width": 216, "height": 384, "duration_ms": 1500},
                "decisions": [
                    {
                        "event_id": "e1",
                        "status": "PLANNED",
                        "start_ms": 0,
                        "end_ms": 1400,
                        "transition_end_ms": 0,
                        "motion": "step",
                        "state": "ARGUMENT",
                        "crop_start": [0, 0, 216, 384],
                        "crop_end": [18, 32, 180, 320],
                        "scale": 1.20,
                    }
                ],
            }

            good = verify(dense, correct, plan)
            self.assertEqual(good["status"], "PASS", good)
            self.assertEqual(good["verified_change_count"], 1)

            bad = verify(dense, noop, plan)
            self.assertEqual(bad["status"], "FAIL", bad)
            self.assertTrue(
                any(e["check"] == "render_does_not_match_planned_crop" for e in bad["errors"]),
                bad,
            )


if __name__ == "__main__":
    unittest.main()
