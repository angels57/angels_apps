{
    "name": "Easy Sign - Certificate Signature",
    "version": "20.0.1.0.1",
    "summary": "Sign the final Easy Sign PDF with the company certificate (.p12/.pfx)",
    "description": """
When a request is completed, the signed PDF is also signed cryptographically
with the certificate configured on the company, so PDF readers show the
signature panel. Without a certificate the flow does not change.
    """,
    "category": "Tools/Sign",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["angels_sign", "certificate"],
    "data": ["views/res_company_views.xml", "views/res_config_settings_views.xml"],
    "images": [
        "static/description/main_screenshot.png",
    ],
    "installable": True,
    "auto_install": False,
}
