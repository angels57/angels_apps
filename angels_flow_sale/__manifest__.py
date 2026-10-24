{
    "name": "Angels Flow - Sales",
    "version": "19.0.1.0.0",
    "summary": "Sales actions for Angels Flow: send the quotation by email from a flow",
    "description": """
Angels Flow - Sales
===================

Adds the actions of Sales to the "Run an Action" step of Angels Flow, on
quotations and sales orders:

* Send the quotation (or the order confirmation) by email to the customer,
  with the template Sales uses, and mark a draft quotation as sent

The buttons of the order (Confirm, Cancel...) are already offered by Angels
Flow. Example: a big quotation needs the approval of the sales manager, then
it is sent to the customer and confirmed, all by itself.

Comes with an example flow, off until you switch it on: Big Quotation
Approval (approval by a sales manager, then sent to the customer and
confirmed).

Installed by itself when Angels Flow and Sales are both installed.
    """,
    "category": "Sales",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["angels_flow", "sale"],
    "data": [
        "data/example_flows.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
