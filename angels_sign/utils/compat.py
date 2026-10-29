"""Version-specific helpers: the only code that differs between the 19.0 and 20.0 branches.

Odoo 20 keeps binary field values as ``BinaryValue`` objects (base64 bytes in 19)
and reads system parameters with typed getters (``get_param`` in 19). Its
``PdfSigner`` takes and returns bytes (streams in 19).
"""
from odoo.tools.binary import BinaryBytes
from odoo.tools.pdf.signature import PdfSigner


def binary_bytes(value):
    """Raw bytes of a binary field value."""
    return value.content if value else b""


def binary_value(raw):
    """Value to write in a binary field from raw bytes."""
    return BinaryBytes(raw) if raw else False


def get_flag(env, key):
    """Boolean system parameter."""
    return env["ir.config_parameter"].sudo().get_bool(key)


def set_flag(env, key, value):
    env["ir.config_parameter"].sudo().set_bool(key, value)


def sign_pdf(pdf_bytes, company, field_name):
    """PDF signed with the company certificate, or None when it has none usable."""
    return PdfSigner(pdf_bytes, company=company).sign_pdf(field_name=field_name)
