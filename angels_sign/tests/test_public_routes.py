import base64
import json

from odoo.tests import HttpCase, tagged

from .common import make_pdf, make_png


@tagged("post_install", "-at_install")
class TestPublicRoutes(HttpCase):

    def setUp(self):
        super().setUp()
        self.env.user.email = "owner@example.test"
        self.request = self.env["sign.request"].create({})
        self.doc = self.env["sign.document"].create({"request_id": self.request.id, "file": make_pdf(1)})
        self.signer = self.env["sign.request.item"].create({
            "request_id": self.request.id, "signer_name": "Ana", "signer_email": "ana@example.test",
        })
        self.other = self.env["sign.request"].create({})
        self.env["sign.document"].create({"request_id": self.other.id, "file": make_pdf(1)})
        self.request.action_send()

    def test_invalid_token(self):
        response = self.url_open("/sign/view/not-a-token")
        self.assertIn("Invalid Link", response.text)
        self.assertEqual(self.url_open("/sign/document/nope/1").status_code, 404)

    def test_view_marks_viewed_and_document_scoped(self):
        token = self.signer.access_token
        response = self.url_open(f"/sign/view/{token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.signer.state, "viewed")
        self.assertEqual(self.url_open(f"/sign/document/{token}/{self.doc.id}").status_code, 200)
        other_doc = self.other.document_ids
        self.assertEqual(self.url_open(f"/sign/document/{token}/{other_doc.id}").status_code, 404)

    def test_post_requires_csrf(self):
        response = self.url_open(f"/sign/submit/{self.signer.access_token}", data={"signature": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.signer.state, "sent")

    def test_verify_page(self):
        self.assertEqual(self.url_open("/sign/verify").status_code, 200)

    def test_signing_tour_like_post(self):
        # A real browser posts the CSRF token taken from the page.
        page = self.url_open(f"/sign/view/{self.signer.access_token}").text
        csrf = page.split('data-csrf="', 1)[1].split('"', 1)[0]
        response = self.url_open(f"/sign/submit/{self.signer.access_token}", data={
            "csrf_token": csrf,
            "signature": "data:image/png;base64," + base64.b64encode(make_png()).decode(),
            "signature_method": "draw",
            "values": "{}",
        })
        self.assertTrue(json.loads(response.text)["success"])
        self.assertEqual(self.signer.state, "signed")
