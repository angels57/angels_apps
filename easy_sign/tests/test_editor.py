import base64

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import EasySignCase, make_pdf


@tagged("post_install", "-at_install")
class TestEditor(EasySignCase):

    def _files(self, *names):
        return [{"name": name, "data": make_pdf(1).decode()} for name in names]

    def test_upload_creates_request_and_opens_editor(self):
        action = self.env["sign.request"].create_from_upload(self._files("a.pdf", "b.pdf"))
        self.assertEqual(action["tag"], "easy_sign_editor")
        request = self.env["sign.request"].browse(action["context"]["active_id"])
        self.assertEqual(request.document_ids.mapped("name"), ["a.pdf", "b.pdf"])
        data = request.get_editor_data()
        self.assertEqual(len(data["documents"]), 2)
        self.assertFalse(data["locked"])

    def test_upload_rejects_non_pdf(self):
        with self.assertRaises(Exception):
            self.env["sign.request"].create_from_upload([{"name": "x.pdf", "data": base64.b64encode(b"nope").decode()}])
        with self.assertRaises(UserError):
            self.env["sign.request"].create_from_upload([])

    def test_template_upload_parties_and_locking(self):
        action = self.env["sign.template"].create_from_upload(self._files("Contract.pdf"))
        template = self.env["sign.template"].browse(action["context"]["active_id"])
        self.assertEqual(template.name, "Contract")
        party = template.editor_add_party()
        self.assertEqual(party["model"], "sign.role")
        self.assertIn(party["id"], template.role_ids.ids)
        doc = template.document_ids
        self.env["sign.item"].create({
            "template_id": template.id, "document_id": doc.id, "role_id": party["id"], "type": "signature",
            "page": 1, "pos_x": 0.1, "pos_y": 0.1, "width": 0.2, "height": 0.05,
        })
        self.assertEqual(template.get_editor_data()["parties"][0]["count"], 1)
        tags = template.editor_set_tags([self.env["sign.tag"].create({"name": "Sales"}).id])
        self.assertEqual(tags[0]["name"], "Sales")
        self.assertEqual(template.editor_set_name("Renamed"), "Renamed")
        # Send from a template creates a request and opens it in the editor.
        send = template.action_send_from_editor()
        self.assertEqual(send["tag"], "easy_sign_editor")
        self.assertTrue(template.get_editor_data()["locked"])
        with self.assertRaises(UserError):
            template.editor_add_party()
        copy = self.env["sign.template"].browse(template.action_edit_copy()["context"]["active_id"])
        self.assertFalse(copy.get_editor_data()["locked"])

    def test_request_parties_and_sign_now(self):
        request = self.env["sign.request"].browse(
            self.env["sign.request"].create_from_upload(self._files("a.pdf"))["context"]["active_id"]
        )
        party = request.editor_add_party()
        signer = self.env["sign.request.item"].browse(party["id"])
        with self.assertRaises(UserError):
            request.action_sign_now()  # current user is not a signer
        signer.write({
            "partner_id": self.env.user.partner_id.id,
            "signer_name": self.env.user.name,
            "signer_email": self.env.user.email,
        })
        self.assertTrue(request.get_editor_data()["can_sign_now"])
        action = request.action_sign_now()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/sign/view/", action["url"])
        self.assertEqual(request.state, "sent")
        with self.assertRaises(UserError):
            request.editor_add_party()

    def test_remove_party_and_contactless_autocomplete(self):
        request = self.env["sign.request"].browse(
            self.env["sign.request"].create_from_upload(self._files("a.pdf"))["context"]["active_id"]
        )
        party = request.editor_add_party()
        signer = self.env["sign.request.item"].browse(party["id"])
        signer.write({"signer_name": "Zoe", "signer_email": "zoe@example.test"})
        field = self.env["sign.item"].create({
            "request_id": request.id, "document_id": request.document_ids.id, "request_item_id": signer.id,
            "type": "text", "page": 1, "pos_x": 0.1, "pos_y": 0.1, "width": 0.3, "height": 0.03,
            "linked_field": "partner_id.email",
        })
        self.assertEqual(field._autocomplete_value(signer), "zoe@example.test")
        request.editor_remove_party(signer.id)
        self.assertFalse(request.request_item_ids)
        self.assertFalse(field.exists())
