from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .common import EasySignCase, make_pdf


class TestSettings(EasySignCase):

    def _enable_terms(self, terms_type):
        settings = self.env["res.config.settings"].create({
            "use_sign_terms": True, "sign_terms_type": terms_type, "sign_terms": "<p>Pay within 30 days</p>",
        })
        settings.execute()

    def test_terms_in_invitation_email(self):
        request, _doc = self.make_request(signers=1)
        signer = request.request_item_ids
        self.assertEqual(request._sign_terms(), {})
        self._enable_terms("plain")
        body = request._render_mail("mail_invitation", {
            "signer": signer, "sign_url": "https://x/sign", "reminder": False, "terms": request._sign_terms(),
        }, signer.partner_id)
        self.assertIn("Pay within 30 days", str(body))
        self._enable_terms("html")
        terms = request._sign_terms()
        self.assertTrue(terms["url"].endswith(f"/sign/terms/{request.company_id.id}"))
        body = request._render_mail("mail_invitation", {
            "signer": signer, "sign_url": "https://x/sign", "reminder": False, "terms": terms,
        }, signer.partner_id)
        self.assertIn(terms["url"], str(body))
        self.assertNotIn("Pay within 30 days", str(body))

    def test_manage_template_access_setting_and_users(self):
        group = self.env.ref("easy_sign.group_manage_template_access")
        self.env["res.config.settings"].create({"group_manage_template_access": True}).execute()
        self.assertIn(group, self.env.ref("base.group_user").implied_ids)
        sign_user = self.env.ref("easy_sign.group_sign_user")
        allowed, other = self.env["res.users"].create([
            {"name": "Allowed", "login": "allowed@example.test", "group_ids": [(6, 0, [sign_user.id])]},
            {"name": "Other", "login": "other@example.test", "group_ids": [(6, 0, [sign_user.id])]},
        ])
        template = self.env["sign.template"].create({
            "name": "NDA", "group_ids": [(6, 0, [self.env.ref("base.group_system").id])],
            "authorized_ids": [(6, 0, [allowed.id])],
        })
        self.env["sign.document"].create({"template_id": template.id, "name": "nda.pdf", "file": make_pdf(1)})
        Template = self.env["sign.template"]
        self.assertIn(template, Template.with_user(allowed).search([]))
        self.assertNotIn(template, Template.with_user(other).search([]))
        template.with_user(allowed)._check_usable()
        with self.assertRaises(UserError):
            template.with_user(other).sudo(False)._check_usable()


@tagged("post_install", "-at_install")
class TestTermsPage(HttpCase):

    def test_terms_page_only_when_enabled(self):
        company = self.env.company
        company.write({"sign_terms": "<p>Our conditions</p>", "sign_terms_type": "html"})
        url = f"/sign/terms/{company.id}"
        self.assertEqual(self.url_open(url).status_code, 404)
        self.env["ir.config_parameter"].sudo().set_param("easy_sign.use_sign_terms", "True")
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Our conditions", response.text)
        self.env.user.email = "owner@example.test"
        request = self.env["sign.request"].create({})
        self.env["sign.document"].create({"request_id": request.id, "file": make_pdf(1)})
        signer = self.env["sign.request.item"].create({
            "request_id": request.id, "signer_name": "Ana", "signer_email": "ana@example.test",
        })
        request.action_send()
        self.assertIn(url, self.url_open(f"/sign/view/{signer.access_token}").text)
