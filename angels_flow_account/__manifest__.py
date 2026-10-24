{
    "name": "Angels Flow - Invoicing",
    "version": "19.0.1.0.0",
    "summary": "Invoicing examples for Angels Flow: follow up overdue invoices every week",
    "description": """
Angels Flow - Invoicing
=======================

Comes with an example flow on customer invoices, off until you switch it on:

* Overdue Invoices Follow-Up: every Monday, the overdue customer invoices
  are sent to the accounting managers; three days later, if an invoice is
  still unpaid, its salesperson gets a task to call the customer

Installed by itself when Angels Flow and Invoicing are both installed.
    """,
    "category": "Accounting/Accounting",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["angels_flow", "account"],
    "data": [
        "data/example_flows.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
