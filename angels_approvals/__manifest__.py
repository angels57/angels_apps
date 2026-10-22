{
    "name": "Angels Approvals - Approval Flows",
    "version": "19.0.1.0.0",
    "summary": "Multi-step approval flows for any Odoo record: conditions, delegation, deadlines and audit trail",
    "description": """
Angels Approvals - Approval Flows for Odoo 19
=============================================

Configure approval flows on any business model and let users request approval
from the record itself ("Request Approval" action).

Features:
---------
* Flows per model with a domain that decides which records they apply to
* Ordered steps; each step has its own condition, approvers and rule
* Approvers by user list, by group or by a user field of the record
* "Any approver" or "all approvers" rule per step
* Delegation of approvals while a user is away
* Deadlines, daily reminders and escalation to another user
* Immutable decision history with comments and "on behalf of"
* Optional server actions run when a request is approved or rejected
* Self-approval blocked by default
    """,
    "category": "Custom",
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
        "data/ir_cron.xml",
        "wizard/request_wizard_views.xml",
        "wizard/decision_wizard_views.xml",
        "views/approval_flow_views.xml",
        "views/approval_request_views.xml",
        "views/approval_delegation_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
