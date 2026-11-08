import os

from odoo import http
from odoo.http import request

from ..utils import catalog, storage

ONE_YEAR = 365 * 24 * 3600


class RunOnWebFiles(http.Controller):
    """Model weights and ONNX Runtime binaries for the browser.

    Public on purpose: they are open weights and runtime files, and public pages (such as a
    signing page) may run tasks too. Only paths listed in the catalog answer; anything else
    is a 404, so nothing else under the storage folder can be read.

    URLs carry the catalog version: an old version is a 404, never older or newer content
    under a URL that browsers keep as immutable.
    """

    @http.route("/angels_runonweb/models/<string:version>/<path:path>", type="http", auth="public",
                methods=["GET"], readonly=True)
    def model_file(self, version, path):
        return self._serve("models", version, path)

    @http.route("/angels_runonweb/runtime/<string:version>/<path:path>", type="http", auth="public",
                methods=["GET"], readonly=True)
    def runtime_file(self, version, path):
        return self._serve("runtime", version, path)

    def _serve(self, kind, version, path):
        entry = catalog.find(kind, path)
        if not entry or version != catalog.version(kind):
            raise request.not_found()
        if storage.is_present(entry):
            local = storage.local_path(entry)
            stat = os.stat(local)
            stream = http.Stream(
                type="path",
                path=local,
                mimetype=entry.mimetype,
                download_name=os.path.basename(local),
                # The content is pinned by its checksum: the hash is a stable etag.
                etag=entry.sha256,
                last_modified=stat.st_mtime,
                size=stat.st_size,
                public=True,
            )
            return stream.get_response(immutable=True, max_age=ONE_YEAR)
        if request.env["angels.runonweb"].sudo()._allow_remote():
            return request.redirect(entry.remote_url, code=302, local=False)
        raise request.not_found()
