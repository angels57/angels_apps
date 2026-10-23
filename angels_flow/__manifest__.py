{
    "name": "Angels Flow - Visual Flows",
    "version": "19.0.1.0.0",
    "summary": "Visual flow engine: steps linked by arrows, approvals, tasks and notifications",
    "description": """
Angels Flow - Visual Flows for Odoo 19
======================================

The flow engine and the flow designer used by Angels Forms, ready for other
modules: a document walks a flow of steps linked by arrows, from Start to an
End.

Features:
---------
* Steps: condition with yes / no, approval, task, notification, back to the
  requester, end; other modules add their own (Angels Forms adds Create Record)
* Approvers by user list or by group, "any approver" or "all approvers" rule
* Activities and chatter messages for every step, self-approval blocked by
  default
* Flow designer: drag steps onto a board, link their outputs with arrows,
  colored Yes / No outputs, "+" on a free output to add the next step, zoom
  and auto arrange

Technical:
----------
* ``angels.flow.node.mixin``: a step of a flow
* ``angels.flow.step.mixin``: a step reached by a document (who must act, the decision)
* ``angels.flow.document.mixin``: the document that walks the flow
* ``FlowEditor`` Owl component, with a registry of step kinds
  (``angels_flow.node_types``) and slots for the host's own settings
    """,
    "category": "Productivity",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["mail", "web"],
    "assets": {
        "web.assets_backend": [
            "angels_flow/static/src/common/*.js",
            "angels_flow/static/src/common/*.xml",
            "angels_flow/static/src/flow_editor/*.js",
            "angels_flow/static/src/flow_editor/*.xml",
            "angels_flow/static/src/flow_editor/*.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
