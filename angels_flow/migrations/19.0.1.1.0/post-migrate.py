from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Flows get an On switch, apart from archiving.

    Flows that were active stay on. The examples were archived to keep them
    off: they come back to the list, off.
    """
    cr.execute("UPDATE angels_flow SET enabled = active WHERE is_example IS NOT TRUE")
    cr.execute("UPDATE angels_flow SET active = TRUE, enabled = FALSE WHERE is_example")
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["angels.flow"].with_context(active_test=False).search([])._sync_automation()
