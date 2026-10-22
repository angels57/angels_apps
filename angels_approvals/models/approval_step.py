from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AngelsApprovalStep(models.Model):
    _name = "angels.approval.step"
    _description = "Approval Flow Step"
    _order = "sequence, id"

    flow_id = fields.Many2one("angels.approval.flow", required=True, ondelete="cascade", index=True)
    model_name = fields.Char(related="flow_id.model_name", string="Model Name")
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    approver_type = fields.Selection(
        [
            ("users", "Specific users"),
            ("group", "Members of a group"),
            ("field", "User set on the record"),
        ],
        string="Approvers",
        required=True,
        default="users",
    )
    user_ids = fields.Many2many(
        "res.users",
        string="Users",
        domain=[("share", "=", False)],
    )
    group_id = fields.Many2one("res.groups", string="Group")
    user_field_id = fields.Many2one(
        "ir.model.fields",
        string="User Field",
        ondelete="cascade",
        domain="[('model', '=', model_name), ('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
        help="Field of the record that holds the approver, for example the salesperson.",
    )
    approval_rule = fields.Selection(
        [("any", "One approver is enough"), ("all", "Every approver must approve")],
        string="Rule",
        required=True,
        default="any",
    )
    condition_domain = fields.Char(
        string="Condition",
        default="[]",
        help="The step only runs for records that match this filter.",
    )
    deadline_days = fields.Integer(
        string="Deadline (days)",
        default=2,
        help="Days the approvers have to decide. 0 means no deadline.",
    )
    escalation_user_id = fields.Many2one(
        "res.users",
        string="Escalate To",
        domain=[("share", "=", False)],
        help="When the deadline passes, this user is added as an approver.",
    )

    @api.constrains("approver_type", "user_ids", "group_id", "user_field_id")
    def _check_approvers(self):
        for step in self:
            if step.approver_type == "users" and not step.user_ids:
                raise ValidationError(_("Step %(step)s needs at least one user.", step=step.name))
            if step.approver_type == "group" and not step.group_id:
                raise ValidationError(_("Step %(step)s needs a group.", step=step.name))
            if step.approver_type == "field" and (
                not step.user_field_id or step.user_field_id.model != step.model_name
            ):
                raise ValidationError(
                    _("Step %(step)s needs a user field of the flow model.", step=step.name)
                )

    @api.constrains("condition_domain")
    def _check_condition_domain(self):
        for step in self:
            try:
                step.flow_id._validate_domain(step.condition_domain)
            except Exception as error:
                raise ValidationError(
                    _("The condition of step %(step)s is not valid: %(error)s",
                      step=step.name, error=error)
                ) from error

    @api.constrains("deadline_days")
    def _check_deadline_days(self):
        if any(step.deadline_days < 0 for step in self):
            raise ValidationError(_("The deadline cannot be negative."))

    def _applies_to(self, record):
        self.ensure_one()
        domain = self.flow_id._eval_domain(self.condition_domain)
        return bool(record.sudo().filtered_domain(domain)) if record else True

    def _get_approvers(self, record):
        """Internal, active users that must decide this step for ``record``."""
        self.ensure_one()
        if self.approver_type == "users":
            users = self.user_ids
        elif self.approver_type == "group":
            users = self.group_id.all_user_ids
        else:
            users = record.sudo()[self.user_field_id.name]
        return users.filtered(lambda u: u.active and not u.share)
