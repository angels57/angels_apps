# Downloads the pinned runtime and models into the cache that the end-to-end browser test
# reads (Odoo blocks internet requests while tests run). Run it once per data folder:
#   odoo shell -c /etc/odoo/odoo.conf -d <db> --no-http < tools/seed_test_cache.py
from unittest.mock import patch

from odoo.addons.angels_runonweb.tests.test_browser import CACHE_DIR
from odoo.addons.angels_runonweb.utils import catalog, storage

with patch.object(storage, "root", return_value=CACHE_DIR):
    for task in catalog.TASKS:
        for entry in catalog.runtime_files() + catalog.task_files(task):
            if not storage.is_present(entry):
                storage.download(entry)
print(f"RunOnWeb test cache ready in {CACHE_DIR}")
