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

    def test_palette_from_field_types(self):
        request = self.env["sign.request"].browse(
            self.env["sign.request"].create_from_upload(self._files("a.pdf"))["context"]["active_id"]
        )
        palette = request.get_editor_data()["palette"]
        self.assertEqual(len(palette), 14)
        company = next(e for e in palette if e["linked"] == "partner_id.parent_id.name")
        self.assertEqual(company["type"], "text")
        self.env["sign.item.type"].create({
            "name": "Employee ID", "base_type": "text", "icon": "fa-id-card", "default_width": 0.2,
        })
        palette = request.get_editor_data()["palette"]
        self.assertIn("Employee ID", [e["label"] for e in palette])

    def test_custom_field_type_end_to_end(self):
        """A field placed from a custom palette entry is saved, signed and printed on the PDF."""
        import io
        from odoo.tools.pdf import PdfReader
        from .common import make_png
        field_type = self.env["sign.item.type"].create({
            "name": "Employee ID", "base_type": "text", "icon": "fa-id-card",
            "default_width": 0.3, "default_height": 0.04, "placeholder": "EMP-000",
        })
        request = self.env["sign.request"].browse(
            self.env["sign.request"].create_from_upload(self._files("a.pdf"))["context"]["active_id"]
        )
        signer = self.env["sign.request.item"].browse(request.editor_add_party()["id"])
        signer.write({"signer_name": "Ana", "signer_email": "ana@example.test"})
        entry = next(e for e in request.get_editor_data()["palette"] if e["id"] == field_type.id)
        item = self.env["sign.item"].create({
            "request_id": request.id, "document_id": request.document_ids.id, "request_item_id": signer.id,
            "item_type_id": entry["id"], "type": entry["type"], "width": entry["size"][0],
            "height": entry["size"][1], "required": entry["required"], "placeholder": entry["placeholder"],
            "page": 1, "pos_x": 0.1, "pos_y": 0.2,
        })
        sig = self.env["sign.item"].create({
            "request_id": request.id, "document_id": request.document_ids.id, "request_item_id": signer.id,
            "type": "signature", "page": 1, "pos_x": 0.1, "pos_y": 0.6, "width": 0.3, "height": 0.08,
        })
        data_item = next(i for i in request.get_editor_data()["items"] if i["id"] == item.id)
        self.assertEqual(data_item["item_type_id"][0], field_type.id)
        public = item._public_data(signer)[0]
        self.assertEqual(public["placeholder"], "EMP-000")
        request.action_send()
        signer._sign(make_png(), "draw", values={item.id: "EMP-4521", sig.id: "1"})
        self.assertEqual(request.state, "signed")
        self.assertEqual(item.value, "EMP-4521")
        pdf = PdfReader(io.BytesIO(base64.b64decode(request.signed_document)))
        self.assertIn("EMP-4521", pdf.pages[0].extract_text())
