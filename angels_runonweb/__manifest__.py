{
    "name": "Angels RunOnWeb",
    "version": "19.0.1.1.1",
    "summary": "On-device AI models in the browser for Odoo, served from your own server",
    "description": """
Angels RunOnWeb
===============

Runs small open AI models inside the browser of each user with runonweb
(WebGPU or WASM). Texts, images and audio never leave the device.

* Library: runonweb 0.1.0, built once with esbuild into static/lib.
* Models and ONNX Runtime binaries are pinned by revision and SHA-256 and
  served by Odoo from its data folder. Downloading them from the internet is
  off by default.
* An ``angels_runonweb`` service lets other addons load a task on demand.
* RunOnWeb Lab (Settings menu): browser diagnostics, server download and a
  panel to try each task.

Tasks: text to emoji (text2emoji-tiny, 4 MB, MIT) and semantic search
(all-MiniLM-L6-v2, 23 MB on WASM or 45 MB on WebGPU, Apache-2.0).
    """,
    "category": "Hidden/Tools",
    "author": "Angels SAS",
    "maintainer": "Angels SAS",
    "license": "LGPL-3",
    "depends": ["base_setup", "web"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "views/runonweb_lab_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "angels_runonweb/static/src/core/*.js",
            "angels_runonweb/static/src/lab/*.js",
            "angels_runonweb/static/src/lab/*.xml",
            "angels_runonweb/static/src/lab/*.scss",
        ],
        "web.assets_unit_tests": [
            "angels_runonweb/static/tests/*.test.js",
        ],
        "web.assets_tests": [
            "angels_runonweb/static/tests/tours/*.js",
        ],
    },
    "installable": True,
    "auto_install": False,
}
