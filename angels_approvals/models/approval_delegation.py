from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AngelsApprovalDelegation(models.Model):
    _name = "angels.approval.delegation"
    _description = "Approval Delegation"
    _order = "date_from desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="Approver",
        required=True,
        default=lambda self: self.env.user,
        domain=[("share", "=", False)],
        index=True,
    )
    delegate_id = fields.Many2one(
        "res.users",
        string="Delegate",
        required=True,
        domain=[("share", "=", False)],
        index=True,
    )
    date_from = fields.Date(string="From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="To", required=True)
    active = fields.Boolean(default=True)
    note = fields.Char()

    @api.constrains("user_id", "delegate_id", "date_from", "date_to")
    def _check_delegation(self):
        for delegation in self:
            if delegation.user_id == delegation.delegate_id:
                raise ValidationError(_("You cannot delegate to yourself."))
            if delegation.delegate_id.share:
                raise ValidationError(_("The delegate must be an internal user."))
            if delegation.date_to < delegation.date_from:
                raise ValidationError(_("The end date must be after the start date."))

    @api.model
    def _active_domain(self, day=None):
        day = day or fields.Date.context_today(self)
        return [("active", "=", True), ("date_from", "<=", day), ("date_to", ">=", day)]

    @api.model
    def _delegators_of(self, user):
        """Users that currently delegate their approvals to ``user``."""
        return self.sudo().search(
            self._active_domain() + [("delegate_id", "=", user.id)]
        ).user_id

    @api.model
    def _delegates_of(self, users):
        """Users that currently act on behalf of ``users``."""
        return self.sudo().search(
            self._active_domain() + [("user_id", "in", users.ids)]
        ).delegate_id

    @api.model_create_multi
    def create(self, vals_list):
        delegations = super().create(vals_list)
        delegations._refresh_pending_lines()
        return delegations

    def write(self, vals):
        res = super().write(vals)
        self._refresh_pending_lines()
        return res

    def _refresh_pending_lines(self):
        lines = self.env["angels.approval.request.line"].sudo().search([
            ("state", "=", "pending"),
            ("approver_ids", "in", self.user_id.ids),
        ])
        lines._refresh_actors()
