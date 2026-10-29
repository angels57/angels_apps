import datetime
import io
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.pdf import PdfReader
from odoo.tools.pdf.signature import PdfSigner

from .common import AngelsSignCase, make_png
from ..utils.compat import binary_bytes, binary_value


def make_pkcs12(password):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Angels Sign Test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"angels_sign", key, cert, None, serialization.BestAvailableEncryption(password.encode()),
    )


@tagged("post_install", "-at_install")
class TestCertificateSignature(AngelsSignCase):

    def _sign_request(self):
        request, _doc = self.make_request(signers=1)
        request.action_send()
        request.request_item_ids._sign(make_png(), "draw")
        self.assertEqual(request.state, "signed")
        return binary_bytes(request.signed_document)

    def _set_certificate(self):
        self.env.company.signing_certificate_id = self.env["certificate.certificate"].create({
            "name": "Angels Sign Test",
            "content": binary_value(make_pkcs12("secret")),
            "pkcs12_password": "secret",
        })

    def test_without_certificate_pdf_is_not_signed(self):
        self.assertNotIn(b"/ByteRange", self._sign_request())

    def test_with_certificate_pdf_is_signed(self):
        self._set_certificate()
        signed = self._sign_request()
        self.assertIn(b"/ByteRange", signed)
        fields = PdfReader(io.BytesIO(signed)).get_fields() or {}
        self.assertIn("Angels Sign", fields)

    def test_signer_failure_keeps_the_pdf(self):
        self._set_certificate()
        with patch.object(PdfSigner, "sign_pdf", side_effect=ValueError("broken")), \
                mute_logger("odoo.addons.angels_sign.models.sign_request_pdf"):
            signed = self._sign_request()
        self.assertTrue(signed.startswith(b"%PDF"))
        self.assertNotIn(b"/ByteRange", signed)
