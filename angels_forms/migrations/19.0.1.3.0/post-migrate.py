"""19.0.1.2.0 -> 19.0.1.3.0: name the Start and End steps in the installed languages.

The flows made from 19.0.1.0.0 rules got English names ("Request Sent",
"Approved"), also for users who work in another language.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["angels.form.node"]._translate_default_names()
