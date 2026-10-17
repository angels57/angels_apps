"""Version-specific helpers: the only code that differs between the 19.0 and 20.0 branches.

Odoo 19 keeps binary fields as base64 bytes; Odoo 20 uses ``BinaryValue`` objects.
"""
import base64


def binary_bytes(value):
    """Raw bytes of a binary field value."""
    return base64.b64decode(value) if value else b""


def binary_value(raw):
    """Value to write in a binary field from raw bytes."""
    return base64.b64encode(raw) if raw else False
