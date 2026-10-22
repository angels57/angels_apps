{
    "name": "Angels Forms - Forms and Flows",
    "version": "19.0.1.0.0",
    "summary": "Build request forms with conditional fields and route them to the right people",
    "description": """
Angels Forms - Forms and Flows for Odoo 19
==========================================

Let any administrator build request forms in a visual designer, and let users
fill them from Odoo. Each answer can change which questions are shown and who
the request goes to. Example included: a travel request.

Features:
---------
* Visual designer: palette of field types, drag to reorder, live preview
* Field types: section, text, long text, number, date, date and time,
  checkbox, choice list, user, contact and file
* Conditional fields and sections ("show only if ...")
* Routing rules with conditions: who approves and who is informed
* Approvers by user list, by group or by a user chosen in the form
* "Any approver" or "all approvers" rule per step
* Notify people when a request is sent or when it is approved
* Activities, chatter and full history on every request
* Self-approval blocked by default
    """,
    "category": "Productivity",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/ir_sequence.xml",
        "data/mail_activity_type.xml",
        "data/travel_form_data.xml",
        "wizard/decision_wizard_views.xml",
        "views/form_views.xml",
        "views/submission_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "angels_forms/static/src/common/*.js",
            "angels_forms/static/src/common/*.xml",
            "angels_forms/static/src/common/*.css",
            "angels_forms/static/src/designer/*.js",
            "angels_forms/static/src/designer/*.xml",
            "angels_forms/static/src/designer/*.css",
            "angels_forms/static/src/fill/*.js",
            "angels_forms/static/src/fill/*.xml",
            "angels_forms/static/src/fill/*.css",
        ],
    },
    "images": [
        "static/description/main_screenshot.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
