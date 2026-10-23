from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestDesigner(FormCase):

    def setUp(self):
        super().setUp()
        self.form = self.env["angels.form"].with_user(self.finance).create({"name": "Vacation"})

    def test_new_form_has_a_start(self):
        data = self.form.get_design_data()
        self.assertEqual([n["type"] for n in data["nodes"]], ["start"])

    def test_save_questions_flow_and_conditions(self):
        data = self.form.get_design_data()
        start_id = data["nodes"][0]["id"]
        data["form"]["name"] = "Vacation Request"
        data["form"]["title_field_id"] = "new_1"
        data["fields"] = [
            {"id": "new_1", "name": "Kind", "type": "selection", "options": ["Paid", "Unpaid"],
             "required": True, "width": "third", "match": "all", "conditions": []},
            {"id": "new_2", "name": "Days", "type": "number", "required": True,
             "width": "two_thirds", "match": "all", "conditions": []},
            {"id": "new_3", "name": "Why unpaid?", "type": "text", "match": "all",
             "conditions": [{"source_id": "new_1", "operator": "=", "value": "Unpaid"}]},
            {"id": "new_4", "name": "HR Notes", "type": "text", "node_id": "new_hr", "match": "all",
             "conditions": []},
        ]
        data["nodes"][0]["links"] = {"next": "new_cond"}
        data["nodes"] += [
            {"id": "new_cond", "name": "Long?", "type": "condition", "x": 300, "y": 100, "match": "all",
             "links": {"yes": "new_hr", "no": "new_end"},
             "conditions": [{"source_id": "new_2", "operator": ">", "value": "5"}]},
            {"id": "new_hr", "name": "HR", "type": "approve", "x": 600, "y": 40, "color": 2,
             "assign_type": "users", "user_ids": self.boss.ids, "approval_rule": "any", "match": "all",
             "links": {"next": "new_end", "reject": False}, "conditions": []},
            {"id": "new_end", "name": "Done", "type": "end", "end_state": "approved", "x": 900, "y": 100,
             "links": {}, "conditions": []},
        ]
        result = self.form.save_design(data)
        kind, days, why, notes = self.form.field_ids
        nodes = {n.name: n for n in self.form.node_ids}
        self.assertEqual(self.form.name, "Vacation Request")
        self.assertEqual(self.form.title_field_id, kind)
        self.assertEqual((kind.width, days.width), ("third", "two_thirds"))
        self.assertEqual(why.condition_ids.source_field_id, kind)
        self.assertEqual(notes.node_id, nodes["HR"])
        self.assertEqual(nodes["Request Sent"].id, start_id)
        self.assertEqual(nodes["Request Sent"].next_id, nodes["Long?"])
        self.assertEqual((nodes["Long?"].yes_id, nodes["Long?"].no_id), (nodes["HR"], nodes["Done"]))
        self.assertEqual(nodes["Long?"].condition_ids.source_field_id, days)
        self.assertEqual((nodes["HR"].pos_x, nodes["HR"].color), (600, 2))

        # Saving again keeps one copy of each condition.
        result = self.form.save_design(result)
        self.assertEqual(len(why.condition_ids), 1)
        self.assertEqual(len(nodes["Long?"].condition_ids), 1)

        # Remove the HR step: its question goes back to the requester.
        result["nodes"] = [n for n in result["nodes"] if n["name"] != "HR"]
        self.form.save_design(result)
        self.assertFalse(nodes["HR"].exists())
        self.assertFalse(notes.node_id)
        self.assertFalse(nodes["Long?"].yes_id)

    def test_new_form_opens_the_designer(self):
        action = self.env["angels.form"].with_user(self.finance).action_new_form()
        self.assertEqual(action["tag"], "angels_forms_designer")
        self.assertTrue(action["context"]["angels_forms_new"])
        form = self.env["angels.form"].browse(action["context"]["active_id"])
        self.assertEqual([n.node_type for n in form.node_ids], ["start"])

    def test_settings_are_saved(self):
        group = self.env.ref("base.group_system")
        data = self.form.get_design_data()
        data["form"].update(icon="fa-truck", color=7, group_ids=group.ids, company_id=False,
                            allow_self_approval=True, description="Couriers")
        result = self.form.save_design(data)
        self.assertEqual((self.form.icon, self.form.color, self.form.description), ("fa-truck", 7, "Couriers"))
        self.assertEqual(self.form.group_ids, group)
        self.assertFalse(self.form.company_id)
        self.assertTrue(self.form.allow_self_approval)
        self.assertEqual(result["form"]["group_ids"], group.ids)
        data["form"]["group_ids"] = []
        self.form.save_design(data)
        self.assertFalse(self.form.group_ids)

    def test_default_step_names_are_translated(self):
        self.env["res.lang"]._activate_lang("es_ES")
        start = self.form.node_ids
        start.with_context(lang="en_US").name = "Request Sent"
        start.with_context(lang="es_ES").name = "Request Sent"
        self.env["angels.form.node"]._translate_default_names()
        self.assertEqual(start.with_context(lang="en_US").name, "Request Sent")
        self.assertNotEqual(start.with_context(lang="es_ES").name, "Request Sent")

    def test_grid_places_are_saved(self):
        data = self.form.get_design_data()
        data["fields"] = [
            {"id": "new_1", "name": "A", "type": "char", "width": "half", "row": 0, "col": 6,
             "match": "all", "conditions": []},
            {"id": "new_2", "name": "B", "type": "char", "width": "quarter", "row": 1, "col": 40,
             "match": "all", "conditions": []},
        ]
        result = self.form.save_design(data)
        a, b = self.form.field_ids
        self.assertEqual((a.row, a.col, a.width), (0, 6, "half"))
        self.assertEqual((b.row, b.col), (1, 11), "the column stays on the grid")
        self.assertEqual((result["fields"][0]["row"], result["fields"][0]["col"]), (0, 6))

    def test_switch_recipients(self):
        data = self.travel.with_user(self.finance).get_design_data()
        manager = next(n for n in data["nodes"] if n["name"] == "Manager Approval")
        manager.update(assign_type="group", group_id=self.env.ref("base.group_user").id)
        self.travel.with_user(self.finance).save_design(data)
        self.assertEqual(self.n["manager"].assign_type, "group")
        manager.update(assign_type="users", user_ids=[])
        with self.assertRaises(ValidationError):
            self.travel.with_user(self.finance).save_design(data)

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

    def test_one_start_only(self):
        with self.assertRaises(ValidationError):
            self.env["angels.form.node"].create({"form_id": self.form.id, "name": "S2", "node_type": "start"})
        with self.assertRaises(ValidationError):
            self.n["manager"].next_id = self.n["start"]

    def test_copy_rebuilds_flow(self):
        copy = self.travel.copy()
        self.assertFalse(copy.published)
        self.assertEqual(copy.title_field_id.form_id, copy)
        passport = copy.field_ids.filtered(lambda f: f.name == "Passport Number")
        self.assertEqual(passport.condition_ids.source_field_id.form_id, copy)
        nodes = {n.name: n for n in copy.node_ids}
        self.assertEqual(len(copy.node_ids), len(self.travel.node_ids))
        self.assertEqual(nodes["Request Sent"].next_id, nodes["Manager Approval"])
        self.assertEqual(nodes["Manager Approval"].reject_id, nodes["Back to Requester"])
        self.assertEqual(nodes["Manager Approval"].user_field_id.form_id, copy)
        self.assertEqual(nodes["Budget over 2,000?"].condition_ids.source_field_id.form_id, copy)
        cost = copy.field_ids.filtered(lambda f: f.name == "Cost Center")
        self.assertEqual(cost.node_id, nodes["Finance Approval"])

    def test_designer_needs_manager(self):
        with self.assertRaises(AccessError):
            self.travel.with_user(self.requester).get_design_data()
        with self.assertRaises(AccessError):
            self.travel.with_user(self.requester).save_design({"form": {"name": "x"}})
