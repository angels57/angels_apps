import re

from odoo.addons.angels_sign.tests.common import make_pdf, make_png
from odoo.addons.sms.tests.common import SMSCase
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestSmsOtp(SMSCase):

    def setUp(self):
        super().setUp()
        self.env.user.email = "owner@example.test"
        self.request = self.env["sign.request"].create({})
        self.env["sign.document"].create({"request_id": self.request.id, "file": make_pdf(1)})
        self.signer = self.env["sign.request.item"].create({
            "request_id": self.request.id, "signer_name": "Ana", "signer_email": "ana@example.test",
            "auth_method": "sms_otp", "signer_phone": "+573001112233",
        })
        self.request.action_send()

    def test_code_goes_through_the_sms_gateway(self):
        # sms_allow_unlink: run Odoo's real sms.sms sending, only IAP is simulated.
        with self.mockSMSGateway(sms_allow_unlink=True):
            self.signer._send_otp()
        self.assertSMSIapSent(["+573001112233"])
        body = self._sms[0]["body"]
        code = re.search(r"\b(\d{6})\b", body).group(1)
        self.signer._check_otp(code)
        self.signer._sign(make_png(), "draw")
        self.assertEqual(self.request.state, "signed")
        self.assertIn("otp_sent", self.request.log_ids.mapped("action"))

    def test_missing_phone(self):
        self.signer.with_context(angels_sign_force=True).signer_phone = False
        with self.mockSMSGateway(), self.assertRaises(UserError):
            self.signer._send_otp()
