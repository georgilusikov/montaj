import unittest

from thz_semantics import ActAnnotation, detect_salience, validate_acts


class SemanticProbeTests(unittest.TestCase):
    def test_deterministic_probes_emit_evidence_not_decisions(self):
        segments = [
            {"start_ms": 0, "end_ms": 1200, "text": "Это не 10 евро, а 30 евро — главная ошибка."},
            {"start_ms": 1200, "end_ms": 2000, "text": "Поэтому никогда так не делайте."},
        ]
        a = detect_salience(segments)
        b = detect_salience(segments)
        self.assertEqual(a, b)
        kinds = {x.kind for x in a}
        self.assertIn("currency", kinds)
        self.assertIn("contrast", kinds)
        self.assertIn("warning", kinds)
        for hit in a:
            self.assertFalse(hasattr(hit, "scale"))
            self.assertFalse(hasattr(hit, "shot_state"))

    def test_act_contract_rejects_overlaps(self):
        with self.assertRaises(ValueError):
            validate_acts((
                ActAnnotation("a", 0, 1000, 0.5, (("story", 0.7),)),
                ActAnnotation("b", 900, 1500, 0.7, (("warning", 0.8),)),
            ))

    def test_act_theme_probabilities_are_validated(self):
        valid = validate_acts((
            ActAnnotation("a", 0, 1000, 0.8, (("story", 0.6), ("warning", 0.3))),
        ))
        self.assertEqual(valid[0].act_id, "a")
        with self.assertRaises(ValueError):
            validate_acts((
                ActAnnotation("a", 0, 1000, 0.8, (("story", 0.8), ("warning", 0.5))),
            ))


if __name__ == "__main__":
    unittest.main()
