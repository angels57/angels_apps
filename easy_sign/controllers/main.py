import json
import logging

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


def _json(payload, status=200):
    return request.make_response(
        json.dumps(payload), headers=[("Content-Type", "application/json")], status=status,
    )


class EasySignController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_signer(self, token):
        if not token:
            return request.env["sign.request.item"]
        return request.env["sign.request.item"].sudo().search([("access_token", "=", token)], limit=1)

    def _is_expired(self, sign_request):
        return bool(sign_request.expiry_date and sign_request.expiry_date < fields.Date.today())

    def _client_info(self):
        return request.httprequest.remote_addr, request.httprequest.headers.get("User-Agent", "")

    def _error_page(self, title, message):
        return request.render("easy_sign.sign_invalid", {"error_title": title, "error_message": message})

    def _blocking_error(self, signer):
        """Return (title, message) when the signer cannot act, else None."""
        if not signer:
            return _("Invalid Link"), _("This signing link is invalid or does not exist.")
        sign_request = signer.request_id
        if sign_request.state == "cancelled" or signer.state == "cancelled":
            return _("Request Cancelled"), _("This signature request has been cancelled.")
        if sign_request.state == "expired" or self._is_expired(sign_request):
            return _("Link Expired"), _("This signing link expired on %s.", sign_request.expiry_date)
        if signer.state == "waiting":
            return _("Not Your Turn Yet"), _("You will receive an email when it is your turn to sign.")
        if signer.state == "pending" or sign_request.state == "draft":
            return _("Invalid Link"), _("This signing link is not active.")
        return None

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    @http.route("/sign/view/<string:token>", type="http", auth="public", sitemap=False)
    def sign_view(self, token, **kwargs):
        signer = self._get_signer(token)
        if signer and signer.state == "signed":
            return request.render("easy_sign.sign_success", {
                "item": signer, "sign_request": signer.request_id, "already_done": True,
            })
        if signer and signer.state == "declined":
            return request.render("easy_sign.sign_declined", {
                "item": signer, "sign_request": signer.request_id, "already_done": True,
            })
        error = self._blocking_error(signer)
        if error:
            return self._error_page(*error)
        sign_request = signer.request_id
        if signer.state == "sent":
            ip, agent = self._client_info()
            signer.write({"state": "viewed"})
            request.env["sign.log"].sudo().create({
                "request_id": sign_request.id,
                "request_item_id": signer.id,
                "action": "viewed",
                "ip_address": ip,
                "user_agent": agent,
            })
        own_fields = sign_request.item_ids.filtered(lambda f: f.request_item_id == signer)
        documents = [{
            "id": doc.id,
            "name": doc.name,
            "url": f"/sign/document/{token}/{doc.id}",
        } for doc in sign_request.document_ids]
        return request.render("easy_sign.sign_page", {
            "item": signer,
            "sign_request": sign_request,
            "token": token,
            "csrf_token": request.csrf_token(),
            "documents_json": json.dumps(documents),
            "fields_json": json.dumps(own_fields._public_data(signer)),
            "needs_signature": not own_fields or "signature" in own_fields.mapped("type"),
            "needs_initials": "initials" in own_fields.mapped("type"),
            "needs_otp": signer.auth_method != "none",
        })

    @http.route("/sign/document/<string:token>/<int:doc_id>", type="http", auth="public", sitemap=False)
    def sign_document(self, token, doc_id, **kwargs):
        signer = self._get_signer(token)
        if self._blocking_error(signer) and not (signer and signer.state in ("signed", "declined")):
            raise request.not_found()
        doc = signer.request_id.document_ids.filtered(lambda d: d.id == doc_id)
        if not doc:
            raise request.not_found()
        pdf = doc._get_bytes()
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", str(len(pdf))),
            ("Cache-Control", "no-store"),
            ("X-Frame-Options", "SAMEORIGIN"),
        ])

    # ------------------------------------------------------------------
    # Actions (JSON)
    # ------------------------------------------------------------------
    @http.route("/sign/otp/<string:token>", type="http", auth="public", methods=["POST"], csrf=True, sitemap=False)
    def sign_otp(self, token, **kwargs):
        signer = self._get_signer(token)
        if self._blocking_error(signer) or signer.state not in ("sent", "viewed"):
            return _json({"success": False, "error": _("This link is not active.")}, 400)
        if signer.auth_method == "none":
            return _json({"success": False, "error": _("No code is needed.")}, 400)
        try:
            signer._send_otp()
        except UserError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        return _json({"success": True})

    @http.route("/sign/submit/<string:token>", type="http", auth="public", methods=["POST"], csrf=True, sitemap=False)
    def sign_submit(self, token, **post):
        signer = self._get_signer(token)
        error = self._blocking_error(signer)
        if error or signer.state not in ("sent", "viewed"):
            return _json({"success": False, "error": (error or (None, _("Already signed.")))[1]}, 400)
        sign_request = signer.request_id
        own_fields = sign_request.item_ids.filtered(lambda f: f.request_item_id == signer)
        method = post.get("signature_method") or "draw"
        if method not in ("draw", "type", "upload"):
            method = "draw"
        try:
            values = json.loads(post.get("values") or "{}")
            if not isinstance(values, dict):
                raise ValueError
        except ValueError:
            return _json({"success": False, "error": _("Invalid data.")}, 400)
        if signer.auth_method != "none":
            try:
                signer._check_otp(post.get("otp"))
            except UserError as exc:
                # No rollback: the failed attempt must stay counted.
                return _json({"success": False, "error": str(exc), "otp": True}, 400)
        try:
            signature = sign_request._validate_image(post.get("signature"))
            needs_signature = not own_fields or "signature" in own_fields.mapped("type")
            if needs_signature and not signature:
                raise UserError(_("Please add your signature."))
            initials = sign_request._validate_image(post.get("initials"))
            if "initials" in own_fields.mapped("type") and not (initials or signature):
                raise UserError(_("Please add your initials."))
            ip, agent = self._client_info()
            signer._sign(signature, method, initials or None, values, ip, agent)
        except UserError as exc:
            request.env.cr.rollback()
            return _json({"success": False, "error": str(exc)}, 400)
        except Exception:
            request.env.cr.rollback()
            _logger.exception("Easy Sign: error saving the signature of signer %s", signer.id)
            return _json({"success": False, "error": _("The signature could not be saved.")}, 500)
        return _json({"success": True, "redirect_url": sign_request.redirect_url or ""})

    @http.route("/sign/decline/<string:token>", type="http", auth="public", methods=["POST"], csrf=True, sitemap=False)
    def sign_decline(self, token, **post):
        signer = self._get_signer(token)
        error = self._blocking_error(signer)
        if error or signer.state not in ("sent", "viewed"):
            return _json({"success": False, "error": (error or (None, _("Already answered.")))[1]}, 400)
        try:
            ip, agent = self._client_info()
            signer.action_decline(reason=(post.get("reason") or "")[:2000], ip_address=ip, user_agent=agent)
        except UserError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        except Exception:
            _logger.exception("Easy Sign: error declining for signer %s", signer.id)
            return _json({"success": False, "error": _("The document could not be declined.")}, 500)
        return _json({"success": True})
