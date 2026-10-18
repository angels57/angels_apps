"""Data and operations of the full-screen PDF editor (requests and templates)."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SignEditorMixin(models.AbstractModel):
    _name = "sign.editor.mixin"
    _description = "Easy Sign PDF Editor"

    # Implemented by each model ------------------------------------------
    def _editor_locked(self):
        raise NotImplementedError

    def _editor_parties(self):
        raise NotImplementedError

    def _editor_party_vals(self, party):
        raise NotImplementedError

    def _editor_new_party(self):
        raise NotImplementedError

    @api.model
    def _editor_party_field(self):
        raise NotImplementedError

    # Shared -------------------------------------------------------------
    def _editor_action(self):
        self.ensure_one()
        xmlid = "angels_sign.action_sign_template_editor" if self._name == "sign.template" else "angels_sign.action_sign_request_editor"
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        action["context"] = {"active_id": self.id}
        action["name"] = self.display_name
        return action

    def action_open_editor(self):
        return self._editor_action()

    @api.model
    def create_from_upload(self, files):
        """``files``: list of {name, data (base64)}. Create the record and open the editor."""
        if not files:
            raise UserError(_("Choose at least one PDF file."))
        record = self.create(self._editor_upload_vals(files))
        record.editor_add_documents(files)
        return record._editor_action()

    @api.model
    def _editor_upload_vals(self, files):
        return {}

    def editor_add_documents(self, files):
        self.ensure_one()
        self._editor_check_editable()
        parent = "template_id" if self._name == "sign.template" else "request_id"
        start = max(self.document_ids.mapped("sequence") or [0]) + 1
        docs = self.env["sign.document"].create([{
            parent: self.id,
            "sequence": start + index,
            "name": f.get("name") or "document.pdf",
            "file": f["data"],
        } for index, f in enumerate(files)])
        return [self._editor_document_vals(doc) for doc in docs]

    def _editor_check_editable(self):
        locked = self._editor_locked()
        if locked:
            raise UserError(locked)

    def _editor_document_vals(self, doc):
        return {
            "id": doc.id,
            "name": doc.name,
            "page_count": doc.page_count,
            "url": f"/web/content/sign.document/{doc.id}/file",
        }

    def get_editor_data(self):
        self.ensure_one()
        party_field = self._editor_party_field()
        items = self.item_ids
        return {
            "model": self._name,
            "id": self.id,
            "name": self.display_name,
            "editable_name": self._name == "sign.template",
            "locked": self._editor_locked() or False,
            "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in self.tag_ids],
            "documents": [self._editor_document_vals(doc) for doc in self.document_ids],
            "parties": [self._editor_party_vals(p) for p in self._editor_parties()],
            "items": items.read([
                "document_id", "page", "pos_x", "pos_y", "width", "height", "type", "required", "readonly",
                "placeholder", "options", "alignment", "linked_field", "item_type_id", party_field,
            ]),
            "palette": self.env["sign.item.type"]._editor_palette(),
            "party_field": party_field,
            "can_send": self._editor_can_send(),
            "is_manager": self.env.user.has_group("angels_sign.group_sign_manager"),
            "properties_view_id": self.env.ref(
                "angels_sign.view_sign_template_properties_form" if self._name == "sign.template"
                else "angels_sign.view_sign_request_properties_form"
            ).id,
            "can_sign_now": self._editor_can_sign_now(),
        }

    def _editor_can_sign_now(self):
        return True

    def _editor_can_send(self):
        return True

    def editor_set_name(self, name):
        self.ensure_one()
        if self._name == "sign.template" and name:
            self.name = name
        return self.display_name

    def editor_add_party(self):
        self.ensure_one()
        self._editor_check_editable()
        return self._editor_party_vals(self._editor_new_party())

    def editor_set_tags(self, tag_ids):
        self.ensure_one()
        self.tag_ids = [(6, 0, tag_ids)]
        return [{"id": t.id, "name": t.name, "color": t.color} for t in self.tag_ids]


class SignRequest(models.Model):
    _name = "sign.request"
    _inherit = ["sign.request", "sign.editor.mixin"]

    def _editor_locked(self):
        if self.state != "draft":
            return _("This request has been sent: documents and fields can no longer be changed.")
        return False

    def _editor_parties(self):
        return self.request_item_ids

    @api.model
    def _editor_party_field(self):
        return "request_item_id"

    def _editor_party_vals(self, signer):
        partner = signer.partner_id
        return {
            "id": signer.id,
            "name": signer.signer_name or partner.name or _("Signer"),
            "email": signer.signer_email or "",
            "color": signer.color,
            "avatar": f"/web/image/res.partner/{partner.id}/avatar_128" if partner else False,
            "count": len(self.item_ids.filtered(lambda f: f.request_item_id == signer)),
            "model": "sign.request.item",
        }

    def _editor_new_party(self):
        count = len(self.request_item_ids) + 1
        return self.env["sign.request.item"].create({
            "request_id": self.id,
            "sequence": count * 10,
            "signer_name": _("Signer %s", count),
        })

    def editor_remove_party(self, party_id):
        self.ensure_one()
        self._editor_check_editable()
        self.request_item_ids.filtered(lambda s: s.id == party_id).unlink()
        return True

    def _editor_can_send(self):
        return self.state in ("draft", "sent") and self.has_pending_signers

    def _editor_can_sign_now(self):
        mine = self.request_item_ids.filtered(
            lambda s: s.partner_id == self.env.user.partner_id and s.state in ("pending", "waiting", "sent", "viewed")
        )
        return bool(mine) and self.state in ("draft", "sent")

    def action_sign_now(self):
        """Step 1 of 2: activate the request for the current user only and open their signing page.

        Nobody else is invited: the other signers stay pending until 'Send' (step 2).
        """
        self.ensure_one()
        mine = self.request_item_ids.filtered(lambda s: s.partner_id == self.env.user.partner_id)
        if not mine:
            raise UserError(_("You are not one of the signers. Add yourself as a signer first."))
        mine = mine.filtered(lambda s: s.state in ("pending", "waiting", "sent", "viewed"))[:1]
        if not mine:
            raise UserError(_("You have already signed this document."))
        if self.state == "draft":
            self._check_ready_to_send(mine)
            self._activate()
        if mine.state in ("pending", "waiting"):
            mine.sudo().write({"state": "sent"})
        return {"type": "ir.actions.act_url", "url": mine.sudo().sign_url, "target": "self"}

    def action_send_from_editor(self):
        self.action_send()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sign.request",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }


class SignTemplate(models.Model):
    _name = "sign.template"
    _inherit = ["sign.template", "sign.editor.mixin"]

    @api.model
    def _editor_upload_vals(self, files):
        name = (files[0].get("name") or _("Template")).rsplit(".", 1)[0]
        return {"name": name}

    def _editor_locked(self):
        if self.request_count:
            return _("This template has been used: documents and fields are locked. Edit a copy to change them.")
        return False

    def _editor_parties(self):
        return (self.role_ids | self.item_ids.role_id).sorted("sequence")

    @api.model
    def _editor_party_field(self):
        return "role_id"

    def _editor_party_vals(self, role):
        partner = role.default_partner_id
        return {
            "id": role.id,
            "name": role.name,
            "email": partner.email or "",
            "color": role.color,
            "avatar": f"/web/image/res.partner/{partner.id}/avatar_128" if partner else False,
            "count": len(self.item_ids.filtered(lambda f: f.role_id == role)),
            "model": "sign.role",
        }

    def _editor_new_party(self):
        existing = self._editor_parties()
        role = self.env["sign.role"].sudo().create({
            "name": _("Signer %s", len(existing) + 1),
            "sequence": (max(existing.mapped("sequence") or [0]) + 10),
            "color": (len(existing) % 11) + 1,
        })
        self.role_ids = [(4, role.id)]
        return role

    def editor_remove_party(self, party_id):
        self.ensure_one()
        self._editor_check_editable()
        self.item_ids.filtered(lambda f: f.role_id.id == party_id).unlink()
        self.role_ids = [(3, party_id)]
        return True

    def action_sign_now(self):
        """Create a request in which the current user signs the first free role (others invited later)."""
        self.ensure_one()
        roles = self._editor_parties()
        free = roles.filtered(lambda r: not r.default_partner_id)[:1] or roles[:1]
        request = self._prepare_request({free: self.env.user.partner_id} if free else {})
        return request.action_sign_now()

    def action_send_from_editor(self):
        """A template is sent by creating a request: it opens in the editor to choose the signers."""
        return self._prepare_request()._editor_action()
