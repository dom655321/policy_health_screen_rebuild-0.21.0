import unittest

from pfia import jsonlogic
from pfia.errors import PredicateError


class TestJsonLogic(unittest.TestCase):
    def test_var_dotted_path(self):
        data = {"entity": {"classes": ["LOCAL_GOV"]}}
        self.assertEqual(jsonlogic.evaluate({"var": "entity.classes"}, data), ["LOCAL_GOV"])

    def test_missing_path_is_none_not_error(self):
        self.assertIsNone(jsonlogic.evaluate({"var": "entity.nope.deeper"}, {"entity": {}}))

    def test_ordering_against_none_fails_closed(self):
        self.assertFalse(jsonlogic.test({"<=": [{"var": "facts.days"}, 365]}, {"facts": {}}))

    def test_some_binds_item_as_context(self):
        expr = {"some": [{"var": "policy.list"}, {"!": {"in": [{"var": ""}, ["A", "B"]]}}]}
        self.assertTrue(jsonlogic.test(expr, {"policy": {"list": ["A", "C"]}}))
        self.assertFalse(jsonlogic.test(expr, {"policy": {"list": ["A", "B"]}}))

    def test_unsupported_operator_rejected(self):
        with self.assertRaises(PredicateError):
            jsonlogic.evaluate({"exec": ["rm"]}, {})


if __name__ == "__main__":
    unittest.main()


class TestThreeValuedLogic(unittest.TestCase):
    """UNKNOWN is a third answer, not a synonym for False."""

    def _tri(self, expr, data):
        return jsonlogic.test_tri(expr, data)

    def test_comparison_against_unknown_is_unknown(self):
        self.assertIs(
            self._tri({"==": [{"var": "e.x"}, True]}, {"e": {"x": jsonlogic.UNKNOWN}}),
            jsonlogic.UNKNOWN,
        )

    def test_conjunction_is_decided_by_a_definite_false(self):
        expr = {"and": [{"==": [{"var": "e.a"}, True]}, {"==": [{"var": "e.b"}, True]}]}
        self.assertFalse(self._tri(expr, {"e": {"a": False, "b": jsonlogic.UNKNOWN}}))
        self.assertIs(self._tri(expr, {"e": {"a": True, "b": jsonlogic.UNKNOWN}}), jsonlogic.UNKNOWN)

    def test_disjunction_is_decided_by_a_definite_true(self):
        expr = {"or": [{"==": [{"var": "e.a"}, True]}, {"==": [{"var": "e.b"}, True]}]}
        self.assertTrue(self._tri(expr, {"e": {"a": True, "b": jsonlogic.UNKNOWN}}))
        self.assertIs(self._tri(expr, {"e": {"a": False, "b": jsonlogic.UNKNOWN}}), jsonlogic.UNKNOWN)

    def test_negation_preserves_unknown(self):
        self.assertIs(
            self._tri({"!": {"==": [{"var": "e.a"}, True]}}, {"e": {"a": jsonlogic.UNKNOWN}}),
            jsonlogic.UNKNOWN,
        )

    def test_membership_over_unknown_is_unknown(self):
        self.assertIs(
            self._tri({"in": ["X", {"var": "e.list"}]}, {"e": {"list": jsonlogic.UNKNOWN}}),
            jsonlogic.UNKNOWN,
        )

    def test_two_valued_test_collapses_unknown_to_false(self):
        self.assertFalse(jsonlogic.test({"==": [{"var": "e.x"}, True]}, {"e": {"x": jsonlogic.UNKNOWN}}))

    def test_unknown_cannot_be_used_as_a_boolean_by_accident(self):
        with self.assertRaises(PredicateError):
            if jsonlogic.UNKNOWN:  # pragma: no cover - the raise is the point
                pass
