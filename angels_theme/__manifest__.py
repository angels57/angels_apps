{
    "name": "Angels Theme - Backend Theme",
    "version": "19.0.1.6.0",
    "summary": "Backend theme: brand colors, restyled tabs, per-user density and an app home screen",
    "description": """
Angels Theme - Backend Theme for Odoo 19
========================================

A backend theme that every app inherits without changing its views.

* Brand color, radius and surfaces defined once as SCSS tokens
* Enterprise-style layout: light navbar with the app icon, views as white
  cards on a gray page, round search box, quieter labels
* Restyled notebook tabs (underline or pill) with a sticky header in forms
* Tabs show a record counter when the page holds one list
* Each form remembers the last tab you opened
* Per-user density (compact, normal, comfortable) and tab style, set in
  My Preferences
* Home screen with the apps as a grid, a search box for apps and menus,
  keyboard navigation and a per-company background (dotted, brand
  gradient, plain or image)
* Home screen layout per user: pin apps to the top, drag to reorder, an
  optional row of recent apps and counters (activities due, documents to sign)
* Phones: the navbar becomes a floating tab bar at the bottom (Home, current
  app, Search and More, which gathers Chat, Activity and Profile in one
  sheet), hidden while scrolling down
    """,
    "category": "Themes/Backend",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [
        "views/home_action.xml",
        "views/res_company_views.xml",
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
            "angels_theme/static/src/scss/layout.scss",
            "angels_theme/static/src/js/*.js",
            "angels_theme/static/src/xml/*.xml",
            "angels_theme/static/src/home/*.scss",
            "angels_theme/static/src/home/*.js",
            "angels_theme/static/src/home/*.xml",
            "angels_theme/static/src/mobile/*.scss",
            "angels_theme/static/src/mobile/*.js",
            "angels_theme/static/src/mobile/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
