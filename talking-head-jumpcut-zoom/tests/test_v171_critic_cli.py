import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from thz_critic.cli import main as critic_cli_main
from thz_critic.registry import CheckRegistry


def all_pass_results(profile: str = "live"):
    registry = CheckRegistry()
    return [
        {"check_id": spec.check_id, "status": "pass"}
        for spec in registry.resolve(profile=profile)
    ]


class CriticCliTests(unittest.TestCase):
    def _payload(self, master: Path):
        return {
            "master_path": str(master),
            "critic_version": "1.7.1-dev.1",
            "manifest_sha256": "b" * 64,
            "analysis_sha256": "c" * 64,
            "renderer_program_sha256": "d" * 64,
            "pass1_independent": True,
            "profile": "live",
            "features": [],
            "results": all_pass_results(),
            "measurements": {"fixture": "critic_cli_test"},
        }

    def test_cli_builds_bound_byte_stable_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = root / "master.mp4"
            master_bytes = b"synthetic-master-fixture\x00\x01\x02"
            master.write_bytes(master_bytes)
            src = root / "critic_input.json"
            dst = root / "critic_report.json"
            src.write_text(json.dumps(self._payload(master)), encoding="utf-8")

            self.assertEqual(critic_cli_main([str(src), str(dst)]), 0)
            first_bytes = dst.read_bytes()
            self.assertTrue(first_bytes.endswith(b"\n"))
            first = json.loads(first_bytes)

            self.assertEqual(first["producer"], "thz_critic")
            self.assertEqual(first["verdict"], "GO")
            self.assertEqual(first["coverage"], 1.0)
            self.assertEqual(
                first["provenance"]["master_sha256"],
                hashlib.sha256(master_bytes).hexdigest(),
            )
            self.assertEqual(first["provenance"]["manifest_sha256"], "b" * 64)
            self.assertEqual(first["provenance"]["analysis_sha256"], "c" * 64)
            self.assertEqual(first["provenance"]["renderer_program_sha256"], "d" * 64)
            self.assertEqual(len(first["provenance"]["script_sha256"]), 64)
            self.assertEqual(len(first["provenance"]["inputs_sha256"]), 64)
            self.assertEqual(len(first["report_hash"]), 64)
            self.assertEqual(first["measurements"]["fixture"], "critic_cli_test")

            self.assertEqual(critic_cli_main([str(src), str(dst)]), 0)
            self.assertEqual(first_bytes, dst.read_bytes())

    def test_cli_requires_explicit_independent_pass1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = root / "master.mp4"
            master.write_bytes(b"master")
            payload = self._payload(master)
            payload["pass1_independent"] = False
            src = root / "critic_input.json"
            dst = root / "critic_report.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pass1_independent"):
                critic_cli_main([str(src), str(dst)])

    def test_cli_rejects_missing_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.mp4"
            payload = self._payload(missing)
            src = root / "critic_input.json"
            dst = root / "critic_report.json"
            src.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "master_path"):
                critic_cli_main([str(src), str(dst)])


if __name__ == "__main__":
    unittest.main()
