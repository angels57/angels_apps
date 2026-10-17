{
    "name": "Easy Sign - Electronic Signature",
    "version": "19.0.2.1.1",
    "summary": "Self-hosted electronic signature: place fields on PDFs, collect signatures, get a certificate",
    "description": """
Easy Sign - Electronic Signature for Odoo 19
=============================================

A self-hosted electronic signature solution that works 100% inside Odoo, with
no external APIs or third-party services required.

Features:
---------
* Place fields on the PDF: signature, initials, text, date, checkbox, multiline
  text, radio, selection, strikethrough and stamp
* Several documents per request (envelopes) and reusable templates with roles
* Signing order, automatic reminders, validity date, copy to contacts
* Signers draw, type or upload their signature, without an Odoo account
* Optional one-time code by email before signing
* "Request Signature" action on the records of the models you choose
* Signed PDF with a verification code on every page and a certificate of
  completion (SHA-256 hashes, IP, browser, chained audit events)
* Public page to verify that a signed PDF has not been modified
* Bridges: easy_sign_sms (code by SMS), easy_sign_certificate (PDF signed
  with the company certificate)

Credits:
--------
Based on the original Easy Sign module by Ahmed Kamal (LGPL-3).
Adapted to Odoo 19 and maintained by Angels SAS.
    """,
    "category": "Tools/Sign",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/ir_sequence.xml",
        "data/ir_cron.xml",
        "data/sign_item_type_data.xml",
        "data/mail_templates.xml",
        "report/certificate_report.xml",
        "templates/sign_page.xml",
        "views/sign_request_views.xml",
        "views/sign_template_views.xml",
        "views/sign_editor_actions.xml",
        "views/sign_editor_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "easy_sign/static/src/icons/icons.css",
            "easy_sign/static/src/editor/*.js",
            "easy_sign/static/src/editor/*.xml",
            "easy_sign/static/src/editor/*.css",
        ],
        "easy_sign.assets_sign_result": [
            "easy_sign/static/src/css/sign_public.css",
            "easy_sign/static/src/css/sign_controls.css",
            "easy_sign/static/src/css/sign_result.css",
            "easy_sign/static/src/css/sign_page.css",
            "easy_sign/static/src/css/sign_fields.css",
            "easy_sign/static/src/js/sign_lang.js",
        ],
        "easy_sign.assets_sign_page": [
            ("include", "easy_sign.assets_sign_result"),
            "easy_sign/static/src/css/sign_document.css",
            "easy_sign/static/src/js/sign_pad.js",
            "easy_sign/static/src/js/sign_pdf.js",
            "easy_sign/static/src/js/sign_public.js",
        ],
    },
    "images": [
        "static/description/main_screenshot.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
