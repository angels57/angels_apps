{
    "name": "Angels Theme - Backend Theme",
    "version": "19.0.1.0.0",
    "summary": "Backend theme: brand colors, restyled tabs and per-user density",
    "description": """
Angels Theme - Backend Theme for Odoo 19
========================================

A backend theme that every app inherits without changing its views.

* Brand color, radius and surfaces defined once as SCSS tokens
* Restyled notebook tabs (underline or pill) with a sticky header in forms
* Tabs show a record counter when the page holds one list
* Each form remembers the last tab you opened
* Per-user density (compact, normal, comfortable) and tab style, set in
  My Preferences
    """,
    "category": "Themes/Backend",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [
        "views/res_users_views.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            ("prepend", "angels_theme/static/src/scss/primary_variables.scss"),
        ],
        "web.assets_backend": [
            "angels_theme/static/src/scss/tokens.scss",
            "angels_theme/static/src/scss/notebook.scss",
            "angels_theme/static/src/scss/density.scss",
            "angels_theme/static/src/js/*.js",
            "angels_theme/static/src/xml/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
