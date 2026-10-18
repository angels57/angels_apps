import hashlib
import threading
import time
from collections import defaultdict, deque

from odoo import _, http
from odoo.http import request

MAX_ATTEMPTS = 20
WINDOW_SECONDS = 600
MAX_UPLOAD = 30 * 1024 * 1024

_attempts = defaultdict(deque)
_lock = threading.Lock()


def _rate_limited(ip):
    now = time.monotonic()
    with _lock:
        hits = _attempts[ip]
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= MAX_ATTEMPTS:
            return True
        hits.append(now)
        return False


class EasySignVerifyController(http.Controller):

    @http.route("/sign/verify", type="http", auth="public", methods=["GET"], sitemap=False)
    def verify_form(self, **kwargs):
        return request.render("angels_sign.verify_page", {"csrf_token": request.csrf_token()})

    @http.route("/sign/verify", type="http", auth="public", methods=["POST"], csrf=True, sitemap=False)
    def verify_submit(self, code=None, document=None, **kwargs):
        values = {"csrf_token": request.csrf_token(), "submitted": True, "code": (code or "").strip().upper()}
        if _rate_limited(request.httprequest.remote_addr):
            values["error"] = _("Too many attempts. Try again in a few minutes.")
            return request.render("angels_sign.verify_page", values)
        Request = request.env["sign.request"].sudo()
        file_hash = None
        if document and getattr(document, "filename", None):
            data = document.read(MAX_UPLOAD + 1)
            if len(data) > MAX_UPLOAD:
                values["error"] = _("The file is too large.")
                return request.render("angels_sign.verify_page", values)
            file_hash = hashlib.sha256(data).hexdigest()
        if values["code"]:
            sign_request = Request.search([("verification_code", "=", values["code"]), ("state", "=", "signed")], limit=1)
        elif file_hash:
            sign_request = Request.search([("signed_document_hash", "=", file_hash), ("state", "=", "signed")], limit=1)
        else:
            values["error"] = _("Enter a verification code or choose the signed PDF.")
            return request.render("angels_sign.verify_page", values)
        values.update({
            "found": bool(sign_request),
            "file_checked": bool(file_hash),
            "file_matches": bool(sign_request and file_hash and file_hash == sign_request.signed_document_hash),
            "completed_date": sign_request.completed_date,
            "signers_count": sign_request.signed_count,
            "chain_ok": bool(sign_request) and sign_request.log_ids._check_chain(),
        })
        return request.render("angels_sign.verify_page", values)
