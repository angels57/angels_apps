"""20.0.2.1.x -> 20.0.2.2.0: angels_sign_sms and angels_sign_certificate merge into angels_sign.

Their fields (``signer_phone``, the ``sms_otp`` verification, the company signing
certificate) now belong to angels_sign. Hand their records over before the models
load, so that the columns and their data stay, drop their views (angels_sign
recreates them) and forget both modules: nobody can uninstall them later and drop
the columns.
"""

BRIDGES = ("angels_sign_sms", "angels_sign_certificate")


def migrate(cr, version):
    cr.execute("""
        DELETE FROM ir_ui_view
         WHERE id IN (SELECT res_id FROM ir_model_data WHERE module IN %s AND model = 'ir.ui.view')
    """, [BRIDGES])
    # Views, and names angels_sign already owns (model_sign_request_item, field_res_company__id...).
    cr.execute("""
        DELETE FROM ir_model_data bridge
         WHERE bridge.module IN %s
           AND (bridge.model = 'ir.ui.view'
                OR EXISTS (SELECT 1 FROM ir_model_data own
                            WHERE own.module = 'angels_sign' AND own.name = bridge.name))
    """, [BRIDGES])
    cr.execute("UPDATE ir_model_data SET module = 'angels_sign' WHERE module IN %s", [BRIDGES])
    cr.execute("DELETE FROM ir_model_data WHERE module = 'base' AND name IN %s",
               [tuple(f"module_{name}" for name in BRIDGES)])
    cr.execute("DELETE FROM ir_module_module WHERE name IN %s", [BRIDGES])
