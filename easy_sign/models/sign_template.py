from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SignTemplate(models.Model):
    _name = "sign.template"
    _description = "Signature Template"
    _order = "name, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    document_ids = fields.One2many("sign.document", "template_id", string="Documents", copy=False)
    item_ids = fields.One2many("sign.item", "template_id", string="Fields", copy=False)
    role_ids = fields.Many2many("sign.role", string="Roles")
    tag_ids = fields.Many2many("sign.tag", string="Tags")
    model_id = fields.Many2one(
        "ir.model", string="Available On", ondelete="set null",
        domain=[("transient", "=", False)],
        help="Adds a 'Request Signature' action on the records of this model.",
    )
    validity_days = fields.Integer(string="Valid For (days)", help="0 means no expiry.")
    reminder_days = fields.Integer(string="Reminder Every (days)")
    signing_order = fields.Boolean(string="Signing Order")
    default_subject = fields.Char(string="Email Subject")
    default_message = fields.Html(string="Invitation Message")
    redirect_url = fields.Char(string="Redirect URL")
    group_ids = fields.Many2many(
        "res.groups", string="Allowed Groups",
        help="Only these groups can use the template. Empty: every Easy Sign user.",
    )
    user_id = fields.Many2one("res.users", string="Responsible", default=lambda self: self.env.user)
    request_ids = fields.One2many("sign.request", "template_id", string="Requests")
    request_count = fields.Integer(compute="_compute_request_count")


    @api.depends("request_ids")
    def _compute_request_count(self):
        data = self.env["sign.request"].with_context(active_test=False)._read_group(
            [("template_id", "in", self.ids)], ["template_id"], ["__count"],
        )
        counts = {tpl.id: count for tpl, count in data}
        for tpl in self:
            tpl.request_count = counts.get(tpl.id, 0)

    # ------------------------------------------------------------------
    # 'Request Signature' action on the configured models
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        templates = super().create(vals_list)
        templates._sync_binding_actions()
        return templates

    def write(self, vals):
        res = super().write(vals)
        if {"model_id", "active"} & set(vals):
            self._sync_binding_actions()
        return res

    def unlink(self):
        if any(tpl.request_count for tpl in self):
            raise UserError(_("Used templates cannot be deleted. Archive them instead."))
        res = super().unlink()
        self._sync_binding_actions()
        return res

    @api.model
    def _sync_binding_actions(self):
        Action = self.env["ir.actions.act_window"].sudo()
        wizard_actions = Action.search([
            ("res_model", "=", "sign.send.wizard"),
            ("binding_model_id", "!=", False),
        ])
        wanted = self.sudo().search([("model_id", "!=", False)]).mapped("model_id")
        wizard_actions.filtered(lambda a: a.binding_model_id not in wanted).unlink()
        existing = wizard_actions.exists().mapped("binding_model_id")
        for model in wanted - existing:
            Action.create({
                "name": _("Request Signature"),
                "res_model": "sign.send.wizard",
                "view_mode": "form",
                "target": "new",
                "binding_model_id": model.id,
                "binding_view_types": "form,list",
                "group_ids": [(4, self.env.ref("easy_sign.group_sign_user").id)],
            })

    # ------------------------------------------------------------------
    # Use / copy
    # ------------------------------------------------------------------
    def _check_usable(self):
        self.ensure_one()
        if not self.document_ids:
            raise UserError(_("The template has no document."))
        if self.group_ids and not (self.group_ids & self.env.user.all_group_ids):
            raise UserError(_("You are not allowed to use this template."))

    def _prepare_request(self, partners_by_role=None, extra_vals=None):
        """Create a draft request from the template. ``partners_by_role``: {role: partner}."""
        self.ensure_one()
        self._check_usable()
        partners_by_role = partners_by_role or {}
        vals = {
            "template_id": self.id,
            "subject": self.default_subject,
            "message": self.default_message,
            "redirect_url": self.redirect_url,
            "reminder_days": self.reminder_days,
            "signing_order": self.signing_order,
            "tag_ids": [(6, 0, self.tag_ids.ids)],
            "expiry_date": self.validity_days and fields.Date.context_today(self) + timedelta(days=self.validity_days),
        }
        vals.update(extra_vals or {})
        request = self.env["sign.request"].create(vals)
        doc_map = {}
        for doc in self.document_ids:
            doc_map[doc.id] = doc.copy({"template_id": False, "request_id": request.id})
        roles = self.role_ids | self.item_ids.role_id
        signer_map = {}
        for seq, role in enumerate(roles.sorted("sequence"), start=1):
            partner = partners_by_role.get(role) or role.default_partner_id
            signer_map[role.id] = self.env["sign.request.item"].create({
                "request_id": request.id,
                "role_id": role.id,
                "sequence": seq * 10,
                "partner_id": partner.id,
                "signer_name": partner.name or role.name,
                "signer_email": partner.email or "",
                "auth_method": role.auth_method,
                "can_delegate": role.can_delegate,
            })
        for item in self.item_ids:
            item.copy({
                "template_id": False,
                "request_id": request.id,
                "document_id": doc_map[item.document_id.id].id,
                "role_id": False,
                "request_item_id": signer_map[item.role_id.id].id if item.role_id else False,
            })
        return request

    def action_create_request(self):
        self.ensure_one()
        return self._prepare_request()._editor_action()

    def action_edit_copy(self):
        self.ensure_one()
        new = self.copy({"name": _("%s (copy)", self.name)})
        doc_map = {}
        for doc in self.document_ids:
            doc_map[doc.id] = doc.copy({"template_id": new.id})
        for item in self.item_ids:
            item.copy({"template_id": new.id, "document_id": doc_map[item.document_id.id].id})
        return new._editor_action()
