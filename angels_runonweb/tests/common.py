import os
import shutil
import tempfile
from unittest.mock import patch

from ..utils import catalog, storage


class StorageMixin:
    """Points the storage folder at a temporary directory for the whole test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage_dir = tempfile.mkdtemp(prefix="angels_runonweb_test_")
        cls.addClassCleanup(shutil.rmtree, cls.storage_dir, ignore_errors=True)
        root_patch = patch.object(storage, "root", return_value=cls.storage_dir)
        root_patch.start()
        cls.addClassCleanup(root_patch.stop)

    def tearDown(self):
        for name in os.listdir(self.storage_dir):
            shutil.rmtree(os.path.join(self.storage_dir, name), ignore_errors=True)
        super().tearDown()

    def write_entry(self, entry, size=None):
        """Put a file of the expected size (fake content) where the server looks for `entry`."""
        path = storage.local_path(entry)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as out:
            out.write(b"x" * (entry.size if size is None else size))
        return path

    def fake_download(self, entry, session=None):
        self.write_entry(entry)

    def set_allow_remote(self, value):
        self.env["ir.config_parameter"].sudo().set_param("angels_runonweb.allow_remote", "True" if value else "False")

    @staticmethod
    def emoji_entry(name="config.json"):
        return catalog.find("models", f"midudev/text2emoji-tiny/{name}")
