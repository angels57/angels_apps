{
    "name": "Angels Flow - Visual Flows",
    "version": "19.0.1.0.0",
    "summary": "Visual flows on any Odoo record: approvals, tasks and notifications, started by hand, "
               "automatically or on a schedule",
    "description": """
Angels Flow - Visual Flows for Odoo 19
======================================

Draw a flow on the records of any model (quotations, invoices, contacts...)
and let it run: it starts by hand from the record, when a record is created
or updated, on a schedule, or a few days before or after a date of the
record. Angels Forms uses the same engine and designer for its requests.

Features:
---------
* Flows app with its own menu: To Do, Runs, Flows
* Starts: by hand (Action menu of the record), on create, on create or update
  of chosen fields, every N hours / days / weeks / months, or around a date
  field; only on the records that match a filter, once per record or again
* Steps: condition on the fields of the record with yes / no, approval, task,
  notification, wait (hours or days), update record (fixed values, today + N
  days, who started the run, empty), run an action (a button of the record
  or a server action), end; other modules add their own (Angels Forms adds
  Create Record, Angels Flow - Sales sends quotations by email)
* Approvers by user list, by group or by a user field of the record
* Approvers by user list or by group, "any approver" or "all approvers" rule
* Activities and chatter messages for every step, self-approval blocked by
  default
* Flow designer: drag steps onto a board, link their outputs with arrows,
  colored Yes / No outputs, "+" on a free output to add the next step, zoom
  and auto arrange

Technical:
----------
* ``angels.flow`` and ``angels.flow.run``: a flow on a model and one record going through it
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
    "depends": ["base_automation", "mail", "web"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/rules.xml",
        "data/flow_data.xml",
        "data/mail_activity_type.xml",
        "data/example_flows.xml",
        "views/flow_views.xml",
        "views/run_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "angels_flow/static/src/common/*.js",
            "angels_flow/static/src/common/*.xml",
            "angels_flow/static/src/flow_editor/*.js",
            "angels_flow/static/src/flow_editor/*.xml",
            "angels_flow/static/src/flow_editor/*.css",
            "angels_flow/static/src/designer/*.js",
            "angels_flow/static/src/designer/*.xml",
            "angels_flow/static/src/designer/*.css",
            "angels_flow/static/src/welcome/*.js",
            "angels_flow/static/src/welcome/*.xml",
            "angels_flow/static/src/welcome/*.css",
        ],
    },
    "images": [
        "static/description/icon.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
