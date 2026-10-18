"""19.0.1.0.0 -> 19.0.2.0.0: one PDF per request becomes sign.document records.

Detach the attachments of the removed ``sign.request.document`` field so that
they survive the field removal; ``post-migrate`` turns them into documents.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_attachment
           SET res_field = 'angels_sign_legacy_document'
         WHERE res_model = 'sign.request' AND res_field = 'document'
    """)
