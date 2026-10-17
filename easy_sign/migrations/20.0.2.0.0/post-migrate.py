from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT column_name FROM information_schema.columns "
               "WHERE table_name = 'sign_request' AND column_name = 'document_name'")
    has_name = bool(cr.fetchone())
    attachments = env["ir.attachment"].search([
        ("res_model", "=", "sign.request"),
        ("res_field", "=", "easy_sign_legacy_document"),
    ])
    for attachment in attachments:
        request = env["sign.request"].browse(attachment.res_id).exists()
        if request:
            name = "document.pdf"
            if has_name:
                cr.execute("SELECT document_name FROM sign_request WHERE id = %s", [request.id])
                name = (cr.fetchone() or [None])[0] or name
            env["sign.document"].with_context(easy_sign_force=True).create({
                "request_id": request.id,
                "name": name,
                "file": attachment.datas,
            })
        attachment.unlink()
    # Existing signers keep working: their old state values are still valid.
