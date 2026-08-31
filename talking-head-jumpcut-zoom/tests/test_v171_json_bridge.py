import json
from pathlib import Path
import tempfile
import unittest

from thz_planner.cli import main as planner_cli_main
from thz_render.cli import main as render_cli_main


class JsonProcessBridgeTests(unittest.TestCase):
    def _fixture(self) -> Path:
        return Path(__file__).resolve().parents[1] / "examples" / "v171_planner_input.json"

    def test_planner_json_compiles_in_separate_renderer_process_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner_out = root / "planner.json"
            renderer_out = root / "renderer.json"

            self.assertEqual(planner_cli_main([str(self._fixture()), str(planner_out)]), 0)
            planner_payload = json.loads(planner_out.read_text(encoding="utf-8"))
            self.assertEqual(
                render_cli_main(
                    [
                        str(planner_out),
                        str(renderer_out),
                        "--fps",
                        "30",
                        "--source-w",
                        "1080",
                        "--source-h",
                        "1920",
                    ]
                ),
                0,
            )
            first_bytes = renderer_out.read_bytes()
            renderer = json.loads(first_bytes)
            self.assertTrue(first_bytes.endswith(b"\n"))
            self.assertEqual(
                renderer["manifest_hash"],
                planner_payload["manifest"]["manifest_hash"],
            )
            self.assertEqual(len(renderer["renderer_program_sha256"]), 64)
            self.assertGreaterEqual(len(renderer["segments"]), 1)
            for segment in renderer["segments"]:
                self.assertIsNotNone(segment["source_start_ms"])
                self.assertIsNotNone(segment["source_end_ms"])

            # Frozen planner JSON must compile to byte-stable renderer JSON.
            self.assertEqual(
                render_cli_main(
                    [
                        str(planner_out),
                        str(renderer_out),
                        "--fps",
                        "30",
                        "--source-w",
                        "1080",
                        "--source-h",
                        "1920",
                    ]
                ),
                0,
            )
            self.assertEqual(first_bytes, renderer_out.read_bytes())

    def test_tampered_planner_json_is_rejected_before_render_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner_out = root / "planner.json"
            tampered = root / "tampered.json"
            renderer_out = root / "renderer.json"
            planner_cli_main([str(self._fixture()), str(planner_out)])
            payload = json.loads(planner_out.read_text(encoding="utf-8"))
            payload["manifest"]["framing_decisions"][0]["crop_start"]["x"] += 2
            tampered.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
                render_cli_main(
                    [
                        str(tampered),
                        str(renderer_out),
                        "--fps",
                        "30",
                        "--source-w",
                        "1080",
                        "--source-h",
                        "1920",
                    ]
                )

    def test_renderer_cli_accepts_bare_manifest_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planner_out = root / "planner.json"
            bare = root / "manifest.json"
            renderer_out = root / "renderer.json"
            planner_cli_main([str(self._fixture()), str(planner_out)])
            payload = json.loads(planner_out.read_text(encoding="utf-8"))
            bare.write_text(json.dumps(payload["manifest"]), encoding="utf-8")
            self.assertEqual(
                render_cli_main(
                    [
                        str(bare),
                        str(renderer_out),
                        "--fps",
                        "30",
                        "--source-w",
                        "1080",
                        "--source-h",
                        "1920",
                    ]
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
