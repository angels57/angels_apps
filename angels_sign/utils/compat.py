"""Version-specific helpers: the only code that differs between the 19.0 and 20.0 branches.

Odoo 20 keeps binary field values as ``BinaryValue`` objects (base64 bytes in 19)
and reads system parameters with typed getters (``get_param`` in 19).
"""
import base64


def binary_bytes(value):
    """Raw bytes of a binary field value."""
    return base64.b64decode(value) if value else b""


def binary_value(raw):
    """Value to write in a binary field from raw bytes."""
    return base64.b64encode(raw) if raw else False


def get_flag(env, key):
    """Boolean system parameter."""
    return bool(env["ir.config_parameter"].sudo().get_param(key))


def set_flag(env, key, value):
    env["ir.config_parameter"].sudo().set_param(key, value)
