from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestDesigner(FormCase):

    def setUp(self):
        super().setUp()
        self.form = self.env["angels.form"].with_user(self.finance).create({"name": "Vacation"})

    def test_save_new_fields_rules_and_conditions(self):
        data = self.form.get_design_data()
        data["form"]["name"] = "Vacation Request"
        data["form"]["title_field_id"] = "new_1"
        data["fields"] = [
            {"id": "new_1", "name": "Kind", "type": "selection", "options": ["Paid", "Unpaid"],
             "required": True, "width": "half", "match": "all", "conditions": []},
            {"id": "new_2", "name": "Days", "type": "number", "required": True,
             "width": "half", "match": "all", "conditions": []},
            {"id": "new_3", "name": "Why unpaid?", "type": "text", "match": "all",
             "conditions": [{"source_id": "new_1", "operator": "=", "value": "Unpaid"}]},
        ]
        data["rules"] = [
            {"id": "new_r", "name": "HR", "rule_type": "approve", "assign_type": "users",
             "user_ids": self.boss.ids, "approval_rule": "any", "match": "all",
             "conditions": [{"source_id": "new_2", "operator": ">", "value": "5"}]},
        ]
        result = self.form.save_design(data)
        kind, days, why = self.form.field_ids
        self.assertEqual(self.form.name, "Vacation Request")
        self.assertEqual(self.form.title_field_id, kind)
        self.assertEqual(kind._option_list(), ["Paid", "Unpaid"])
        self.assertEqual(why.condition_ids.source_field_id, kind)
        self.assertEqual(self.form.rule_ids.condition_ids.source_field_id, days)
        self.assertEqual(result["fields"][2]["conditions"][0]["source_id"], kind.id)

        # Saving again keeps one copy of each condition.
        result = self.form.save_design(result)
        self.assertEqual(len(why.condition_ids), 1)
        self.assertEqual(len(self.form.rule_ids.condition_ids), 1)

        # Reorder, edit and remove in a second save.
        result["fields"] = [result["fields"][1], result["fields"][0]]
        result["fields"][0]["name"] = "Number of Days"
        result["rules"] = []
        self.form.save_design(result)
        self.assertEqual(self.form.field_ids.mapped("name"), ["Number of Days", "Kind"])
        self.assertFalse(why.exists())
        self.assertFalse(self.form.rule_ids)

    def test_answered_fields_are_archived_not_deleted(self):
        submission = self.fill()
        destination = self.f["destination"]
        data = self.travel.with_user(self.finance).get_design_data()
        data["fields"] = [f for f in data["fields"] if f["id"] != destination.id]
        data["form"]["title_field_id"] = False
        self.travel.with_user(self.finance).save_design(data)
        self.assertTrue(destination.exists())
        self.assertFalse(destination.active)
        self.assertIn("Madrid", str(submission.answers_html))

    def test_condition_order_checked_on_save(self):
        data = self.form.get_design_data()
        data["fields"] = [
            {"id": "new_1", "name": "A", "type": "char", "match": "all",
             "conditions": [{"source_id": "new_2", "operator": "set", "value": ""}]},
            {"id": "new_2", "name": "B", "type": "char", "match": "all", "conditions": []},
        ]
        with self.assertRaises(ValidationError):
            self.form.save_design(data)

    def test_copy_rebuilds_conditions(self):
        copy = self.travel.copy()
        passport = copy.field_ids.filtered(lambda f: f.name == "Passport Number")
        self.assertEqual(passport.condition_ids.source_field_id.form_id, copy)
        self.assertEqual(copy.title_field_id.form_id, copy)
        self.assertTrue(all(c.source_field_id.form_id == copy for c in copy.rule_ids.condition_ids))
        self.assertFalse(copy.published)

    def test_designer_needs_manager(self):
        with self.assertRaises(AccessError):
            self.travel.with_user(self.requester).get_design_data()
        with self.assertRaises(AccessError):
            self.travel.with_user(self.requester).save_design({"form": {"name": "x"}})
