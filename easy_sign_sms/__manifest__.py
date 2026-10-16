{
    "name": "Easy Sign - SMS Verification",
    "version": "19.0.1.0.0",
    "summary": "Verify Easy Sign signers with a one-time code sent by SMS",
    "description": """
Adds "Email link + SMS code" as a verification method for Easy Sign signers.
The code is sent with Odoo SMS (IAP): it consumes Odoo SMS credits.
    """,
    "category": "Tools/Sign",
    "author": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["easy_sign", "sms"],
    "data": ["views/sign_request_views.xml"],
    "installable": True,
    "auto_install": False,
}
