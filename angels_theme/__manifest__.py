{
    "name": "Angels Theme - Backend Theme",
    "version": "19.0.1.14.0",
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
  app, Search, Chat, Activity and Profile), hidden while scrolling down; the
  app tab shows its sections as an accordion, and chat and activity open as
  bottom sheets. The primary action of the view ("New", "Upload PDF"...)
  moves from the control panel to a raised button in the middle of the bar,
  and search, view, pages, actions and "more" to a round button over it, on
  the right, that opens them upwards
* Every dialog and wizard: rounded frame, the app icon in the header, the
  form as a card, the primary button on the right, a statusbar shown as
  steps and, on phones, a bottom sheet
* Controls: white secondary buttons, a brand focus ring, thin scrollbars,
  tags and status badges as soft pills, empty states as a card, brand
  checkboxes, radios and switches, and horizontal radios as segments
* Motion in CSS only: buttons that lift and press, menus, dialogs and
  notifications that ease in, rows and cards that rise in, a tab underline
  that grows, an invalid field that shakes; off with reduced motion
* Inputs as boxes with a brand focus ring, a bar on required fields and a
  clear error state; read-only fields and editable lists stay plain
* Menus, the many2one autocomplete and popovers with rounded corners and
  brand hovers; notifications with an icon by type; a date picker with
  today ringed and the selection filled
* Views: breadcrumbs, pager and view switcher as segments, search facets
  as brand pills, the form statusbar as steps, group rows and totals in
  lists, one2many lines framed as a sub-table with a totals card, and the
  settings page as cards of rows with switches
* Kanban: cards apart with rounded corners and a hover lift, column headers
  with a slim progress bar, a framed quick create, a guide in empty columns
  and folded columns as a gray strip
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
            "angels_theme/static/src/scss/controls.scss",
            "angels_theme/static/src/scss/fields.scss",
            "angels_theme/static/src/scss/popups.scss",
            "angels_theme/static/src/scss/views.scss",
            "angels_theme/static/src/scss/kanban.scss",
            "angels_theme/static/src/scss/motion.scss",
            "angels_theme/static/src/js/*.js",
            "angels_theme/static/src/xml/*.xml",
            "angels_theme/static/src/home/*.scss",
            "angels_theme/static/src/home/*.js",
            "angels_theme/static/src/home/*.xml",
            "angels_theme/static/src/mobile/*.scss",
            "angels_theme/static/src/mobile/*.js",
            "angels_theme/static/src/mobile/*.xml",
            "angels_theme/static/src/dialog/*.scss",
            "angels_theme/static/src/dialog/*.js",
            "angels_theme/static/src/dialog/*.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
