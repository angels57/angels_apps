import hashlib
import os
import re

import requests

from odoo.tests import BaseCase

from ..utils import catalog, storage
from .common import StorageMixin

SHA256 = re.compile(r"^[0-9a-f]{64}$")


class FakeResponse:
    def __init__(self, body, status=200):
        self.body = body
        self.status_code = status

    def iter_content(self, size):
        for start in range(0, len(self.body), 3):
            yield self.body[start:start + 3]


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def entry_for(body, path="midudev/text2emoji-tiny/test.json"):
    return catalog.CatalogFile("models", path, "https://example.test/" + path,
                               hashlib.sha256(body).hexdigest(), len(body), "application/json")


class TestCatalog(BaseCase):

    def test_every_file_is_pinned(self):
        entries = catalog.runtime_files() + catalog.task_files("emoji")
        self.assertTrue(entries)
        for entry in entries:
            self.assertRegex(entry.sha256, SHA256, entry.path)
            self.assertGreater(entry.size, 0, entry.path)
            self.assertTrue(entry.remote_url.startswith("https://"), entry.path)
            self.assertNotIn("/resolve/main/", entry.remote_url)
            self.assertNotIn("..", entry.path)
        revision = catalog.TASKS["emoji"]["revision"]
        self.assertTrue(all(revision in e.remote_url for e in catalog.task_files("emoji")))
        self.assertTrue(all(catalog.ORT_VERSION in e.remote_url for e in catalog.runtime_files()))

    def test_find_only_returns_listed_paths(self):
        self.assertEqual(self.emoji_config().path, "midudev/text2emoji-tiny/config.json")
        self.assertEqual(catalog.find("runtime", "ort-wasm-simd-threaded.asyncify.wasm").mimetype, "application/wasm")
        for kind, path in [
            ("models", "midudev/text2emoji-tiny/README.md"),
            ("models", "midudev/text2emoji-tiny/../../../etc/passwd"),
            ("models", "ort-wasm-simd-threaded.asyncify.wasm"),
            ("runtime", "midudev/text2emoji-tiny/config.json"),
            ("static", "midudev/text2emoji-tiny/config.json"),
        ]:
            self.assertIsNone(catalog.find(kind, path), (kind, path))

    def test_sizes(self):
        self.assertEqual(catalog.task_size("emoji"), 4375353)
        self.assertEqual(catalog.runtime_size(), 26914834)

    @staticmethod
    def emoji_config():
        return catalog.find("models", "midudev/text2emoji-tiny/config.json")


class TestStorage(StorageMixin, BaseCase):

    def test_local_path_stays_in_the_storage_folder(self):
        entry = self.emoji_entry("onnx/encoder_model_quantized.onnx")
        path = storage.local_path(entry)
        self.assertTrue(path.startswith(self.storage_dir + os.sep))
        self.assertTrue(path.endswith(os.path.join("models", "midudev", "text2emoji-tiny", "onnx", "encoder_model_quantized.onnx")))

    def test_is_present_checks_the_size(self):
        entry = self.emoji_entry()
        self.assertFalse(storage.is_present(entry))
        self.write_entry(entry, size=entry.size - 1)
        self.assertFalse(storage.is_present(entry))
        self.write_entry(entry)
        self.assertTrue(storage.is_present(entry))
        storage.remove(entry)
        self.assertFalse(storage.is_present(entry))
        storage.remove(entry)  # removing twice is fine

    def test_download_writes_the_verified_file(self):
        body = b'{"model_type": "t5"}'
        entry = entry_for(body)
        session = FakeSession(FakeResponse(body))
        storage.download(entry, session=session)
        with open(storage.local_path(entry), "rb") as f:
            self.assertEqual(f.read(), body)
        url, kwargs = session.urls[0]
        self.assertEqual(url, entry.remote_url)
        self.assertTrue(kwargs["stream"])
        self.assertEqual(kwargs["timeout"], storage.TIMEOUT)
        self.assertEqual(self.leftovers(entry), [])

    def test_download_rejects_a_wrong_checksum(self):
        entry = entry_for(b"good content")
        with self.assertRaisesRegex(storage.DownloadError, "checksum"):
            storage.download(entry, session=FakeSession(FakeResponse(b"evil content")))
        self.assertFalse(os.path.exists(storage.local_path(entry)))
        self.assertEqual(self.leftovers(entry), [])

    def test_download_stops_when_the_file_is_too_large(self):
        entry = entry_for(b"small")
        with self.assertRaisesRegex(storage.DownloadError, "larger"):
            storage.download(entry, session=FakeSession(FakeResponse(b"much larger than expected")))
        self.assertEqual(self.leftovers(entry), [])

    def test_download_reports_http_and_network_errors(self):
        entry = entry_for(b"abc")
        with self.assertRaisesRegex(storage.DownloadError, "404"):
            storage.download(entry, session=FakeSession(FakeResponse(b"", status=404)))
        with self.assertRaisesRegex(storage.DownloadError, "offline"):
            storage.download(entry, session=FakeSession(error=requests.ConnectionError("offline")))
        self.assertFalse(os.path.exists(storage.local_path(entry)))

    def test_a_failed_download_keeps_the_previous_file(self):
        body = b"version one"
        entry = entry_for(body)
        storage.download(entry, session=FakeSession(FakeResponse(body)))
        with self.assertRaises(storage.DownloadError):
            storage.download(entry, session=FakeSession(FakeResponse(b"broken")))
        with open(storage.local_path(entry), "rb") as f:
            self.assertEqual(f.read(), body)

    @staticmethod
    def leftovers(entry):
        folder = os.path.dirname(storage.local_path(entry))
        return [name for name in os.listdir(folder) if name.startswith(".part-")] if os.path.isdir(folder) else []
