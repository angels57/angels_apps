import os
import re

from odoo.tests import HttpCase, tagged
from odoo.tools.misc import file_path

from ..utils import catalog
from .common import StorageMixin

LIB = "/angels_runonweb/static/lib/runonweb"


def url(kind, path, version=None):
    return f"/angels_runonweb/{kind}/{version or catalog.version(kind)}/{path}"


@tagged("post_install", "-at_install")
class TestRoutes(StorageMixin, HttpCase):

    def get(self, url):
        # No session: the files are public, like on a signing page.
        return self.url_open(url, allow_redirects=False)

    def test_unknown_paths_are_not_found(self):
        for address in [
            url("models", "midudev/text2emoji-tiny/README.md"),
            url("models", "other/model/config.json"),
            url("runtime", "ort.min.js"),
            url("models", "midudev/text2emoji-tiny/..%2F..%2F..%2Fodoo.conf"),
            url("runtime", "..%2F..%2Fmodels%2Fmidudev%2Ftext2emoji-tiny%2Fconfig.json"),
            # Without a version, as before 19.0.1.1.1.
            "/angels_runonweb/models/midudev/text2emoji-tiny/config.json",
        ]:
            with self.subTest(url=address):
                self.assertEqual(self.get(address).status_code, 404)

    def test_missing_file_without_internet_downloads(self):
        self.set_allow_remote(False)
        self.assertEqual(self.get(url("models", "midudev/text2emoji-tiny/config.json")).status_code, 404)

    def test_missing_file_redirects_to_the_pinned_source(self):
        self.set_allow_remote(True)
        for kind, path in [
            ("models", "midudev/text2emoji-tiny/onnx/encoder_model_quantized.onnx"),
            ("models", "Xenova/all-MiniLM-L6-v2/onnx/model_fp16.onnx"),
            ("runtime", "ort-wasm-simd-threaded.asyncify.wasm"),
        ]:
            with self.subTest(path=path):
                response = self.get(url(kind, path))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.headers["Location"], catalog.find(kind, path).remote_url)

    def test_local_file_is_served_with_long_cache(self):
        entry = self.emoji_entry()
        self.write_entry(entry)
        self.set_allow_remote(True)  # a local file always wins over the internet
        response = self.get(url("models", "midudev/text2emoji-tiny/config.json"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"x" * entry.size)
        self.assertEqual(response.headers["Content-Type"].split(";")[0], "application/json")
        self.assertIn("immutable", response.headers["Cache-Control"])
        self.assertIn("public", response.headers["Cache-Control"])
        self.assertIn(entry.sha256, response.headers["ETag"])

    def test_runtime_mimetypes(self):
        for name, mimetype in [
            ("ort-wasm-simd-threaded.asyncify.mjs", "text/javascript"),
            ("ort-wasm-simd-threaded.asyncify.wasm", "application/wasm"),
        ]:
            self.write_entry(catalog.find("runtime", name))
            response = self.get(url("runtime", name))
            with self.subTest(name=name):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Content-Type"].split(";")[0], mimetype)

    def test_incomplete_file_is_not_served(self):
        entry = self.emoji_entry("tokenizer.json")
        self.write_entry(entry, size=10)
        self.set_allow_remote(False)
        self.assertEqual(self.get(url("models", "midudev/text2emoji-tiny/tokenizer.json")).status_code, 404)

    def test_another_version_is_not_found(self):
        """A URL of another catalog version never gets the current content (H1)."""
        entry = self.emoji_entry()
        self.write_entry(entry)
        self.write_entry(catalog.find("runtime", "ort-wasm-simd-threaded.asyncify.wasm"))
        self.set_allow_remote(True)
        for address in [
            url("models", "midudev/text2emoji-tiny/config.json", version="000000000000"),
            url("runtime", "ort-wasm-simd-threaded.asyncify.wasm", version=catalog.version("models")),
            url("runtime", "ort-wasm-simd-threaded.asyncify.wasm", version=catalog.ORT_VERSION),
        ]:
            with self.subTest(url=address):
                self.assertEqual(self.get(address).status_code, 404)
        self.assertEqual(self.get(url("models", "midudev/text2emoji-tiny/config.json")).status_code, 200)

    def test_range_requests(self):
        """Transformers.js asks for parts of the files to check them."""
        entry = self.emoji_entry("tokenizer.json")
        self.write_entry(entry)
        response = self.url_open(url("models", "midudev/text2emoji-tiny/tokenizer.json"), headers={"Range": "bytes=0-9"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b"x" * 10)

    def test_library_build_is_served(self):
        folder = os.path.dirname(file_path("angels_runonweb/static/lib/runonweb/emoji.js"))
        for entry in ("emoji.js", "embed.js"):
            response = self.get(f"{LIB}/{entry}")
            self.assertEqual(response.status_code, 200)
            # Every chunk the entry imports is part of the addon.
            chunks = re.findall(r'(?:from|import\()\s*"(\./chunks/[^"]+)"', response.text)
            self.assertGreaterEqual(len(chunks), 2, entry)
            for chunk in chunks:
                self.assertTrue(os.path.isfile(os.path.join(folder, chunk)), chunk)
        for name in ("runonweb", "transformers", "onnxruntime-web"):
            self.assertTrue(os.path.isfile(os.path.join(folder, "licenses", f"{name}.LICENSE")), name)
