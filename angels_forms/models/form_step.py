from odoo import _, fields, models
from odoo.exceptions import UserError

from .form_condition import is_set


class AngelsFormStep(models.Model):
    """One flow step reached by one request: an approval, a task or a notification."""

    _name = "angels.form.step"
    _inherit = ["angels.flow.step.mixin"]
    _description = "Form Request Step"
    _order = "submission_id, sequence, id"
    _flow_document = "submission_id"

    submission_id = fields.Many2one(
        "angels.form.submission", required=True, ondelete="cascade", index=True, readonly=True,
    )
    node_id = fields.Many2one("angels.form.node", string="Flow Step", ondelete="set null", readonly=True)
    user_ids = fields.Many2many(
        "res.users", "angels_form_step_user_rel", "step_id", "user_id",
        string="People", readonly=True,
    )
    approved_by_ids = fields.Many2many(
        "res.users", "angels_form_step_approved_rel", "step_id", "user_id",
        string="Approved By", readonly=True,
    )

    def _fields_to_fill(self):
        self.ensure_one()
        return self.node_id.field_ids if self.node_id else self.env["angels.form.field"]

    def _flow_before_done(self):
        self._check_filled()

    def _check_filled(self):
        """The questions of this step that are shown and required must be answered."""
        self.ensure_one()
        submission = self.submission_id
        visible, values = submission.form_id._visible_values(submission._answer_values())
        missing = (self._fields_to_fill() & visible).filtered(
            lambda f: f.required and f.field_type != "section" and not is_set(values.get(f.id))
        )
        if missing:
            raise UserError(_("Please answer: %(fields)s", fields=", ".join(missing.mapped("name"))))
