import unittest

from thz_critic import (
    CheckRegistry,
    CheckResult,
    CriticProvenance,
    build_bound_provenance,
    build_critic_report,
    canonical_report_json,
    expected_inputs_sha256,
    hash_named_inputs,
)


class CriticReportTests(unittest.TestCase):
    def _provenance(self, *, inputs_sha256=None):
        manifest = "b" * 64
        analysis = "c" * 64
        renderer = "d" * 64
        inputs = inputs_sha256 or hash_named_inputs(
            {
                "manifest_sha256": manifest,
                "analysis_sha256": analysis,
                "renderer_program_sha256": renderer,
            }
        )
        return CriticProvenance(
            critic_version="1.7.1-dev.1",
            script_sha256="a" * 64,
            master_sha256="e" * 64,
            inputs_sha256=inputs,
            pass1_independent=True,
            manifest_sha256=manifest,
            analysis_sha256=analysis,
            renderer_program_sha256=renderer,
        )

    def _results(self, registry):
        return [
            CheckResult(spec.check_id, "pass")
            for spec in registry.resolve(profile="live")
        ]

    def test_bound_builder_derives_inputs_hash(self):
        provenance = build_bound_provenance(
            critic_version="1.7.1-dev.1",
            script_sha256="a" * 64,
            master_sha256="e" * 64,
            manifest_sha256="b" * 64,
            analysis_sha256="c" * 64,
            renderer_program_sha256="d" * 64,
        )
        self.assertEqual(provenance.inputs_sha256, expected_inputs_sha256(provenance))
        self.assertTrue(provenance.pass1_independent)

    def test_report_is_byte_stable_for_reordered_results(self):
        registry = CheckRegistry()
        results = self._results(registry)
        a = build_critic_report(
            registry=registry,
            results=results,
            profile="live",
            provenance=self._provenance(),
        )
        b = build_critic_report(
            registry=registry,
            results=reversed(results),
            profile="live",
            provenance=self._provenance(),
        )
        self.assertEqual(a["report_hash"], b["report_hash"])
        self.assertEqual(canonical_report_json(a), canonical_report_json(b))
        self.assertEqual(a["verdict"], "GO")
        self.assertEqual(a["coverage"], 1.0)

    def test_report_rejects_unbound_inputs_hash(self):
        registry = CheckRegistry()
        with self.assertRaisesRegex(ValueError, "inputs_sha256"):
            build_critic_report(
                registry=registry,
                results=self._results(registry),
                profile="live",
                provenance=self._provenance(inputs_sha256="f" * 64),
            )

    def test_named_hashing_prevents_semantic_swap(self):
        left = hash_named_inputs(
            {"manifest_sha256": "1" * 64, "analysis_sha256": "2" * 64}
        )
        right = hash_named_inputs(
            {"manifest_sha256": "2" * 64, "analysis_sha256": "1" * 64}
        )
        self.assertNotEqual(left, right)


if __name__ == "__main__":
    unittest.main()
