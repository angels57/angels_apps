import base64
from datetime import date, datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import FormCase


@tagged("post_install", "-at_install")
class TestCreateRecord(FormCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record_node = cls.env["angels.form.node"].create({
            "form_id": cls.travel.id,
            "name": "Create Contact",
            "node_type": "record",
            "record_model": "res.partner",
            "next_id": cls.n["end"].id,
            "mapping_ids": [
                (0, 0, {"field_name": "name", "source": "template",
                        "value": "Trip to {%s} ({reference})" % cls.f["destination"].id}),
                (0, 0, {"field_name": "comment", "source": "question", "question_id": cls.f["reason"].id}),
                (0, 0, {"field_name": "user_id", "source": "requester"}),
                (0, 0, {"field_name": "color", "source": "question", "question_id": cls.f["budget"].id}),
                (0, 0, {"field_name": "email", "source": "value", "value": "trips@example.com"}),
                (0, 0, {"field_name": "type", "source": "value", "value": "Invoice"}),
            ],
        })
        cls.n["booking"].next_id = cls.record_node
        cls.finance.group_ids += cls.env.ref("base.group_partner_manager")

    def approve_small_trip(self, **answers):
        submission = self.fill(**answers)
        self.decide(submission, self.boss)
        self.step(submission, self.desk, booking_ref="IB-1")
        return submission

    def test_approved_request_creates_the_record_once(self):
        upload = {"name": "ticket.png", "data": base64.b64encode(b"png").decode()}
        submission = self.approve_small_trip(files=[upload])
        self.assertEqual(submission.state, "approved")
        link = submission.link_ids
        self.assertEqual((len(link), link.res_model, link.node_id), (1, "res.partner", self.record_node))
        partner = self.env["res.partner"].browse(link.res_id)
        self.assertEqual(partner.name, f"Trip to Madrid ({submission.name})")
        self.assertEqual(link.name, partner.display_name)
        self.assertIn("Customer visit", partner.comment)
        self.assertEqual(partner.user_id, self.requester)
        self.assertEqual(partner.color, 800)
        self.assertEqual((partner.email, partner.type), ("trips@example.com", "invoice"))
        files = self.env["ir.attachment"].search([("res_model", "=", "res.partner"), ("res_id", "=", partner.id)])
        self.assertEqual(files.mapped("name"), ["ticket.png"])
        self.assertIn("Create Contact", submission.message_ids[1].body)
        self.assertEqual(submission.link_count, 1)
        self.assertEqual(submission.action_view_links()["res_id"], partner.id)
        # The requester sees what the request created.
        self.assertEqual(submission.with_user(self.requester).link_ids, link)
        # Walking the step again does not create a second contact.
        self.assertFalse(self.record_node._create_record(submission, {}))
        self.assertEqual(len(submission.link_ids), 1)

    def test_missing_required_field_stops_the_approval(self):
        self.record_node.write({
            "name": "Create Tag",
            "record_model": "res.partner.category",
            "mapping_ids": [(5,), (0, 0, {"field_name": "name", "source": "question",
                                          "question_id": self.f["hotel_notes"].id})],
        })
        submission = self.fill()
        self.decide(submission, self.boss)
        with self.assertRaisesRegex(UserError, "Create Tag.*Name is empty"):
            self.step(submission, self.desk, booking_ref="IB-1")

    def test_database_refusal_is_explained(self):
        # A contact needs a name (SQL check): the error names the step, the request stays usable.
        self.record_node.mapping_ids.filtered(lambda m: m.field_name == "name").write({
            "source": "question", "question_id": self.f["hotel_notes"].id, "value": False,
        })
        self.record_node.mapping_ids.filtered(lambda m: m.field_name == "type").value = "Contact"
        submission = self.fill()
        self.decide(submission, self.boss)
        with self.assertRaisesRegex(UserError, "Create Contact could not create the Contact"), \
                mute_logger("odoo.sql_db"):
            self.step(submission, self.desk, booking_ref="IB-1")
        self.assertEqual(submission.state, "pending")

    def test_values_are_converted_to_the_field(self):
        Mapping = self.env["angels.form.mapping"]
        node = self.env["angels.form.node"].new({"form_id": self.travel.id, "node_type": "record",
                                                 "record_model": "mail.activity"})
        submission = self.fill()
        departure = self.f["departure"]

        def value(field_name, raw, **vals):
            mapping = Mapping.new(dict({"node_id": node, "field_name": field_name, "source": "question",
                                        "question_id": departure.id}, **vals))
            return mapping._compute_value(submission, {departure.id: raw})

        self.assertEqual(value("date_deadline", datetime(2026, 11, 2, 10, 0)), date(2026, 11, 2))
        self.assertEqual(value("summary", date(2026, 11, 2)), "2026-11-02")
        self.assertIsNone(value("date_deadline", False), "empty answer: the default applies")
        self.assertEqual(value("user_id", False, source="value", value=str(self.boss.id)), self.boss.id)
        with self.assertRaises(ValidationError):
            value("date_deadline", False, source="value", value="not a date")

    def test_technical_models_are_refused(self):
        for model in ("res.users", "ir.config_parameter", "angels.form.link", "mail.thread"):
            with self.assertRaises(ValidationError, msg=model):
                self.record_node.record_model = model

    def test_designer_needs_the_right_to_create_the_record(self):
        Form = self.env["angels.form"].with_user(self.finance)
        models_ = {m["model"] for m in Form.get_record_models()}
        self.assertIn("res.partner", models_)
        self.assertNotIn("res.country", models_, "countries are for administrators")
        self.assertNotIn("res.users", models_)
        data = self.travel.with_user(self.finance).get_design_data()
        node = next(n for n in data["nodes"] if n["id"] == self.record_node.id)
        node["record_model"] = "res.country"
        node["mappings"] = [{"field": "name", "source": "value", "value": "Atlantis"}]
        with self.assertRaises(AccessError):
            self.travel.with_user(self.finance).save_design(data)

    def test_record_fields_for_the_designer(self):
        fields_ = self.env["angels.form"].with_user(self.finance).get_record_fields("res.partner")
        tag_fields = self.env["angels.form"].with_user(self.finance).get_record_fields("res.partner.category")
        self.assertEqual(tag_fields[0]["name"], "name", "required fields first")
        self.assertTrue(tag_fields[0]["required"])
        by_name = {f["name"]: f for f in fields_}
        self.assertEqual(by_name["user_id"]["relation"], "res.users")
        self.assertNotIn("create_uid", by_name)
        self.assertNotIn("message_follower_ids", by_name)
        self.assertNotIn("display_name", by_name)

    def test_designer_round_trip(self):
        designer = self.travel.with_user(self.finance)
        data = designer.get_design_data()
        node = next(n for n in data["nodes"] if n["id"] == self.record_node.id)
        self.assertEqual(node["record_model"], "res.partner")
        self.assertEqual(len(node["mappings"]), 6)
        mapping_ids = self.record_node.mapping_ids.ids
        designer.save_design(data)
        self.assertEqual(self.record_node.mapping_ids.ids, mapping_ids, "unchanged mappings are kept")
        # A new question, used in the text of a field before it is saved.
        data["fields"].append({"id": "new_1", "name": "Project", "type": "char", "row": 99, "col": 0,
                               "width": "half", "options": [], "conditions": []})
        node["mappings"][0]["value"] = "{new_1} / {reference}"
        data = designer.save_design(data)
        project = self.travel.field_ids.filtered(lambda f: f.name == "Project")
        self.assertEqual(self.record_node.mapping_ids[0].value, "{%s} / {reference}" % project.id)

    def test_copy_points_at_the_new_questions(self):
        copy = self.travel.copy()
        node = copy.node_ids.filtered(lambda n: n.node_type == "record")
        self.assertEqual(node.record_model, "res.partner")
        destination = copy.field_ids.filtered(lambda f: f.name == self.f["destination"].name)
        self.assertEqual(node.mapping_ids[0].value, "Trip to {%s} ({reference})" % destination.id)
        reason = node.mapping_ids.filtered(lambda m: m.field_name == "comment").question_id
        self.assertEqual(reason.form_id, copy)
