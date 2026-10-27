import os
from unittest.mock import patch

from odoo.addons.web.tests.test_js import unit_test_error_checker
from odoo.tests import HttpCase, tagged
from odoo.tools import config

from ..utils import catalog, storage

# Real downloads are kept between runs so the end-to-end test fetches them once.
CACHE_DIR = os.path.join(config["data_dir"], "angels_runonweb_test_cache")


@tagged("post_install", "-at_install")
class TestBrowser(HttpCase):

    def test_hoot_suite(self):
        """JS unit tests of the loader and the lab (runonweb mocked)."""
        self.browser_js(
            # Regular expression filter: only the suites of this addon.
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000&filter=%2F%5E%40angels_runonweb%5C%2F%2F",
            "", "", login="admin", timeout=600,
            success_signal="[HOOT] Test suite succeeded", error_checker=unit_test_error_checker,
        )

    def test_lab_runs_the_real_model(self):
        """End to end: Odoo serves the pinned files and Chrome runs text2emoji-tiny.

        Tests cannot reach the internet, so the files come from a cache filled beforehand
        with tools/seed_test_cache.py.
        """
        with patch.object(storage, "root", return_value=CACHE_DIR):
            missing = [e.path for e in catalog.runtime_files() + catalog.task_files("emoji") if not storage.is_present(e)]
            if missing:
                self.skipTest(f"run tools/seed_test_cache.py first, missing: {', '.join(missing)}")
            self.env["ir.config_parameter"].sudo().set_param("angels_runonweb.allow_remote", "False")
            self.start_tour("/odoo/action-angels_runonweb.action_runonweb_lab", "angels_runonweb_lab_tour",
                            login="admin", timeout=300)
