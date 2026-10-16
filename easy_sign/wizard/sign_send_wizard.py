from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SignSendWizard(models.TransientModel):
    _name = "sign.send.wizard"
    _description = "Request a Signature from a Record"

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    template_id = fields.Many2one("sign.template", string="Template", domain="[('id', 'in', allowed_template_ids)]")
    allowed_template_ids = fields.Many2many("sign.template", compute="_compute_allowed_template_ids")
    file = fields.Binary(string="PDF")
    file_name = fields.Char()
    signer_ids = fields.One2many("sign.send.wizard.signer", "wizard_id", string="Signers")
    message = fields.Html(string="Message")
    expiry_date = fields.Date(string="Valid Until")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        model, res_id = ctx.get("active_model"), ctx.get("active_id")
        if model and res_id:
            res.update({"res_model": model, "res_id": res_id})
            templates = self._templates_for(model)
            if len(templates) == 1:
                res["template_id"] = templates.id
        return res

    @api.model
    def _templates_for(self, model):
        templates = self.env["sign.template"].search([("model_id.model", "=", model)])
        user_groups = self.env.user.all_group_ids
        return templates.filtered(lambda t: not t.group_ids or t.group_ids & user_groups)

    @api.depends("res_model")
    def _compute_allowed_template_ids(self):
        for wizard in self:
            wizard.allowed_template_ids = self._templates_for(wizard.res_model) if wizard.res_model else False

    def _record_partner(self):
        record = self.env[self.res_model].browse(self.res_id).exists()
        if not record:
            return self.env["res.partner"]
        if record._name == "res.partner":
            return record
        partner = record["partner_id"] if "partner_id" in record._fields else False
        return partner if partner and partner._name == "res.partner" else self.env["res.partner"]

    @api.onchange("template_id")
    def _onchange_template_id(self):
        partner = self._record_partner()
        tpl = self.template_id
        lines = [(5, 0, 0)]
        if tpl:
            roles = (tpl.role_ids | tpl.item_ids.role_id).sorted("sequence")
            for idx, role in enumerate(roles):
                default = role.default_partner_id or (partner if idx == 0 else False)
                lines.append((0, 0, {"role_id": role.id, "partner_id": default and default.id}))
            self.message = tpl.default_message
            if tpl.validity_days:
                self.expiry_date = fields.Date.add(fields.Date.context_today(self), days=tpl.validity_days)
        elif partner:
            lines.append((0, 0, {"partner_id": partner.id}))
        self.signer_ids = lines

    def action_send(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id).exists()
        record.check_access("read")
        missing = self.signer_ids.filtered(lambda s: not s.partner_id.email)
        if not self.signer_ids or missing:
            raise UserError(_("Every signer needs a contact with an email address."))
        origin = {
            "res_model": self.res_model,
            "res_id": self.res_id,
            "message": self.message,
            "expiry_date": self.expiry_date,
        }
        if self.template_id:
            partners = {line.role_id: line.partner_id for line in self.signer_ids if line.role_id}
            sign_request = self.template_id._prepare_request(partners, origin)
        else:
            if not self.file:
                raise UserError(_("Choose a template or a PDF."))
            sign_request = self.env["sign.request"].create(origin)
            self.env["sign.document"].create({
                "request_id": sign_request.id,
                "name": self.file_name or "document.pdf",
                "file": self.file,
            })
            for seq, line in enumerate(self.signer_ids, start=1):
                self.env["sign.request.item"].create({
                    "request_id": sign_request.id,
                    "sequence": seq * 10,
                    "partner_id": line.partner_id.id,
                    "signer_name": line.partner_id.name,
                    "signer_email": line.partner_id.email,
                })
        sign_request.action_send()
        if hasattr(record, "message_post"):
            record.message_post(body=_("Signature requested: %s", sign_request.name), message_type="notification")
        return {"type": "ir.actions.act_window_close"}


class SignSendWizardSigner(models.TransientModel):
    _name = "sign.send.wizard.signer"
    _description = "Signer of a Signature Request Wizard"

    wizard_id = fields.Many2one("sign.send.wizard", required=True, ondelete="cascade")
    role_id = fields.Many2one("sign.role", string="Role", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Contact")
