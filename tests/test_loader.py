import unittest
from pathlib import Path

from pfia import loader

ROOT = Path(__file__).resolve().parents[1] / "data" / "registers"


class TestLoader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = loader.load(ROOT)

    def test_both_schedules_load(self):
        self.assertEqual({r.schedule for r in self.rs.registers}, {"A", "B"})

    def test_all_references_resolve(self):
        self.assertGreater(len(self.rs.controls), 10)

    def test_no_weights_and_explicit_band(self):
        """ADR 0010: no weights; every control states its band (no silent default)."""
        for control in self.rs.controls:
            self.assertFalse(hasattr(control, "weight"), control.control_id)
            self.assertIn(control.policy_text_expectation, ("REQUIRED", "RECOMMENDED", "RECOMMENDED_NOT_REQUIRED"))
            for e in control.elements:
                self.assertFalse(hasattr(e, "weight"), control.control_id)

    def test_class_expansion_is_transitive(self):
        expanded = self.rs.expand_classes(["WATER_DISTRICT_36_49"])
        self.assertIn("DISTRICT_ART3_52B_ART16_59", expanded)
        self.assertIn("LOCAL_GOV", expanded)

    def test_schedule_b_controls_are_instrument_gated(self):
        for control in self.rs.controls:
            if control.schedule == "B":
                self.assertIn("instrument_authorized", control.activation, control.control_id)


if __name__ == "__main__":
    unittest.main()
