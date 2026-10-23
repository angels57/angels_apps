{
    "name": "Angels Forms - Forms and Flows",
    "version": "19.0.1.3.0",
    "summary": "Request forms with conditional fields and a visual approval flow",
    "description": """
Angels Forms - Forms and Flows for Odoo 19
==========================================

Let any administrator build request forms in a visual designer, and let users
fill them from Odoo. Each answer can change which questions are shown and who
the request goes to. Example included: a travel request.

Features:
---------
* Everything in the designer: open a form and you land in it, with a
  Settings tab (who can fill it, company, title, self-approval) and an
  icon and color picker
* Visual designer: drag questions anywhere on a 12-column grid, stretch their
  edge to change the width (1/4 to full), edit them in place with the toolbar
  on the question, and switch the same view to a live preview (as the
  requester or as any step)
* Field types: section, text, long text, number, date, date and time,
  checkbox, choice list, user, contact and file
* Conditional fields and sections ("show only if ...")
* Flow designer: steps linked by arrows on a board (condition with yes / no,
  approval, task, notification, back to the requester, end), zoom and auto
  arrange
* Each approval or task step can fill its own questions, shown in its color
  (for example Finance fills the cost center, the travel desk the booking)
* Approvers by user list, by group or by a user chosen in the form
* "Any approver" or "all approvers" rule per step, self-approval blocked by default
* Activities, chatter and full history on every request
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
