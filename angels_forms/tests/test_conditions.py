from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestConditions(FormCase):

    def visible(self, **overrides):
        raw = self.answers(**overrides)
        fields, values = self.travel._visible_values(raw)
        return fields, values

    def test_field_shown_only_when_condition_matches(self):
        fields, values = self.visible(type="National", passport="X123")
        self.assertNotIn(self.f["passport"], fields)
        self.assertFalse(values[self.f["passport"].id], "hidden answers are dropped")
        fields, values = self.visible(type="International", passport="X123")
        self.assertIn(self.f["passport"], fields)
        self.assertEqual(values[self.f["passport"].id], "X123")

    def test_boolean_condition(self):
        fields, _values = self.visible(hotel=True, nights=2)
        self.assertIn(self.f["nights"], fields)
        fields, values = self.visible(hotel=False, nights=2)
        self.assertNotIn(self.f["nights"], fields)
        self.assertFalse(values[self.f["nights"].id])

    def test_hidden_section_hides_its_questions(self):
        section = self.env.ref("angels_forms.travel_section_budget")
        section.condition_ids = [(0, 0, {
            "source_field_id": self.f["destination"].id, "operator": "=", "value": "nowhere",
        })]
        fields, values = self.visible(budget=900)
        self.assertNotIn(section, fields)
        self.assertNotIn(self.f["budget"], fields)
        self.assertFalse(values[self.f["budget"].id])
        self.assertIn(self.f["reason"], fields)

    def test_operators(self):
        Condition = self.env["angels.form.condition"]
        budget = self.f["budget"]
        cases = [
            (">", "500", 800, True), (">", "800", 800, False), (">=", "800", 800, True),
            ("<", "1000", 800, True), ("<=", "799", 800, False), ("=", "800", 800, True),
            ("!=", "800", 800, False), ("set", "", 800, True), ("not_set", "", False, True),
            ("!=", "800", False, True),
        ]
        for operator, value, actual, expected in cases:
            condition = Condition.new({"source_field_id": budget.id, "operator": operator, "value": value})
            self.assertEqual(condition._matches({budget.id: budget._normalize(actual)}), expected,
                             f"{actual} {operator} {value}")
        text = Condition.new({"source_field_id": self.f["destination"].id, "operator": "contains", "value": "mad"})
        self.assertTrue(text._matches({self.f["destination"].id: "Madrid"}), "case insensitive")
        date = Condition.new({"source_field_id": self.f["departure"].id, "operator": ">", "value": "2026-11-01"})
        self.assertTrue(date._matches({self.f["departure"].id: self.f["departure"]._normalize("2026-11-02")}))

    def test_condition_must_point_backwards(self):
        with self.assertRaises(ValidationError):
            self.f["type"].condition_ids = [(0, 0, {
                "source_field_id": self.f["budget"].id, "operator": ">", "value": "1",
            })]

    def test_operator_must_fit_type(self):
        with self.assertRaises(ValidationError):
            self.f["budget"].condition_ids = [(0, 0, {
                "source_field_id": self.f["destination"].id, "operator": ">", "value": "1",
            })]

    def test_invalid_number(self):
        with self.assertRaises(ValidationError):
            self.fill(budget="lots")
