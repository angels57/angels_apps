import io

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.pdf import PdfReader

from .common import AngelsSignCase, make_pdf, make_png
from ..utils.compat import binary_bytes, binary_value


@tagged("post_install", "-at_install")
class TestRequestFlow(AngelsSignCase):

    def test_send_and_sign_without_fields(self):
        request, _doc = self.make_request(signers=1)
        request.action_send()
        self.assertEqual(request.state, "sent")
        self.assertTrue(request.document_hash and request.verification_code)
        signer = request.request_item_ids
        self.assertEqual(signer.state, "sent")
        with self.assertRaises(UserError):
            request.document_ids.name = "changed.pdf"
        signer._sign(make_png(), "draw", ip_address="1.1.1.1", user_agent="test")
        self.assertEqual(request.state, "signed")
        self.assertTrue(signer.signer_hash)
        signed = binary_bytes(request.signed_document)
        self.assertNotEqual(signed, binary_bytes(request.document_ids.file))
        self.assertGreaterEqual(len(PdfReader(io.BytesIO(signed)).pages), 2)
        self.assertTrue(request.log_ids._check_chain())

    def test_signing_order_and_fields(self):
        request, doc = self.make_request(order=True)
        first, second = request.request_item_ids.sorted("sequence")
        sig = self.add_field(request, doc, first)
        text = self.add_field(request, doc, first, "text", pos_y=0.2, height=0.03)
        radio = self.add_field(request, doc, first, "radio", pos_y=0.3, options="Yes\nNo")
        self.add_field(request, doc, second, "signature", pos_x=0.6)
        request.action_send()
        self.assertEqual((first.state, second.state), ("sent", "waiting"))
        with self.assertRaises(UserError):
            first._sign(make_png(), "draw", values={sig.id: "1", radio.id: "Yes"})
        with self.assertRaises(UserError):
            first._sign(make_png(), "draw", values={sig.id: "1", text.id: "x", radio.id: "Maybe"})
        first._sign(make_png(), "type", values={sig.id: "1", text.id: "Hello", radio.id: "Yes"})
        self.assertEqual(text.value, "Hello")
        self.assertEqual(second.state, "sent")
        second._sign(make_png(), "upload", values={request.item_ids.filtered(lambda f: f.request_item_id == second).id: "1"})
        self.assertEqual(request.state, "signed")

    def test_fields_of_other_signer_rejected(self):
        request, doc = self.make_request()
        first, second = request.request_item_ids
        other = self.add_field(request, doc, second)
        self.add_field(request, doc, first)
        request.action_send()
        with self.assertRaises(UserError):
            first._sign(make_png(), "draw", values={other.id: "1"})

    def test_decline_cancels_request(self):
        request, _doc = self.make_request()
        request.action_send()
        first, second = request.request_item_ids
        first.action_decline(reason="<b>no</b>")
        self.assertEqual(request.state, "cancelled")
        self.assertEqual(second.state, "cancelled")
        self.assertEqual(first.state, "declined")

    def test_expiry_cron(self):
        request, _doc = self.make_request(signers=1)
        request.action_send()
        request.expiry_date = "2000-01-01"
        self.env["sign.request"]._cron_expire_requests()
        self.assertEqual(request.state, "expired")
        self.assertEqual(request.request_item_ids.state, "cancelled")

    def test_reminder_cron(self):
        request, _doc = self.make_request(signers=1, reminder_days=1)
        request.action_send()
        signer = request.request_item_ids
        signer.sudo().last_reminder_date = "2000-01-01 00:00:00"
        self.assertEqual(self.env["sign.request"]._cron_send_reminders(), 1)
        self.assertIn("reminded", request.log_ids.mapped("action"))
        self.assertEqual(self.env["sign.request"]._cron_send_reminders(), 0)

    def test_otp(self):
        request, _doc = self.make_request(signers=1)
        signer = request.request_item_ids
        signer.auth_method = "email_otp"
        request.action_send()
        signer._send_otp()
        with self.assertRaises(UserError):
            signer._check_otp("000000")
        signer.sudo().otp_hash = signer._otp_digest("123456")
        signer._check_otp("123456")
        with self.assertRaises(UserError):
            signer._check_otp("123456")  # single use

    def test_delegation(self):
        request, _doc = self.make_request(signers=1)
        signer = request.request_item_ids
        request.action_send()
        with self.assertRaises(UserError):
            signer.signer_email = "x@example.test"
        signer.with_context(angels_sign_force=True).can_delegate = True
        token = signer.access_token
        signer.signer_email = "new@example.test"
        self.assertNotEqual(signer.access_token, token)
        self.assertIn("delegated", request.log_ids.mapped("action"))

    def test_audit_log_is_immutable(self):
        request, _doc = self.make_request(signers=1)
        request.action_send()
        with self.assertRaises(UserError):
            request.log_ids[:1].notes = "tampered"
        with self.assertRaises(UserError):
            request.log_ids.unlink()

    def test_invalid_pdf_and_field_outside_page(self):
        request = self.env["sign.request"].create({})
        with self.assertRaises(ValidationError):
            self.env["sign.document"].create({"request_id": request.id, "file": binary_value(b"hello")})
        doc = self.env["sign.document"].create({"request_id": request.id, "file": make_pdf(1)})
        signer = self.env["sign.request.item"].create({"request_id": request.id, "signer_name": "A", "signer_email": "a@x.test"})
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.add_field(request, doc, signer, pos_x=0.9, width=0.3)
        with self.assertRaises(ValidationError):
            self.add_field(request, doc, signer, page=3)

    def test_rotated_page_overlay(self):
        request = self.env["sign.request"].create({})
        doc = self.env["sign.document"].create({"request_id": request.id, "file": make_pdf(1, rotate=90)})
        signer = self.env["sign.request.item"].create({"request_id": request.id, "signer_name": "A", "signer_email": "a@x.test"})
        self.add_field(request, doc, signer, "text", pos_y=0.1, height=0.04)
        request.action_send()
        signer._sign(make_png(), "draw", values={request.item_ids.id: "Rotated"})
        self.assertEqual(request.state, "signed")

    def test_template_and_wizard(self):
        role_a, role_b = self.env["sign.role"].create([{"name": "Client"}, {"name": "Company"}])
        template = self.env["sign.template"].create({
            "name": "Contract", "role_ids": [(6, 0, (role_a | role_b).ids)], "validity_days": 5,
            "model_id": self.env.ref("base.model_res_partner").id,
        })
        doc = self.env["sign.document"].create({"template_id": template.id, "file": make_pdf(1)})
        self.env["sign.item"].create({
            "template_id": template.id, "document_id": doc.id, "role_id": role_a.id, "type": "text",
            "page": 1, "pos_x": 0.1, "pos_y": 0.1, "width": 0.3, "height": 0.03,
            "linked_field": "partner_id.city", "readonly": True,
        })
        action = self.env["ir.actions.act_window"].search([
            ("res_model", "=", "sign.send.wizard"), ("binding_model_id.model", "=", "res.partner"),
        ])
        self.assertTrue(action)
        wizard = self.env["sign.send.wizard"].with_context(
            active_model="res.partner", active_id=self.partner_a.id,
        ).new({})
        self.assertEqual(wizard.template_id, template)
        wizard._onchange_template_id()
        wizard.signer_ids.filtered(lambda line: line.role_id == role_b).partner_id = self.partner_b
        wizard.action_send()
        request = template.request_ids
        self.assertEqual(request.res_id, self.partner_a.id)
        self.assertEqual(request.state, "sent")
        field = request.item_ids
        self.assertEqual(field._autocomplete_value(field.request_item_id), "Cali")
        with self.assertRaises(UserError):
            doc.name = "locked.pdf"
        copy_action = template.action_edit_copy()
        copy = self.env["sign.template"].browse(copy_action["context"]["active_id"])
        self.assertEqual(len(copy.item_ids), 1)
        copy.document_ids.name = "editable.pdf"
