from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .form_rule import RULE_TYPES


class AngelsFormStep(models.Model):
    """One rule applied to one request: an approval step or a notification."""

    _name = "angels.form.step"
    _description = "Form Request Step"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one(
        "angels.form.submission", required=True, ondelete="cascade", index=True, readonly=True,
    )
    rule_id = fields.Many2one("angels.form.rule", string="Routing Rule", ondelete="set null", readonly=True)
    sequence = fields.Integer(readonly=True)
    name = fields.Char(string="Step", required=True, readonly=True)
    step_type = fields.Selection(RULE_TYPES, string="Action", required=True, readonly=True)
    approval_rule = fields.Selection(
        [("any", "One person is enough"), ("all", "Everyone must approve")],
        string="Rule", required=True, default="any", readonly=True,
    )
    state = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("pending", "To Approve"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("notified", "Informed"),
            ("skipped", "Skipped"),
        ],
        required=True, default="waiting", readonly=True, index=True,
    )
    user_ids = fields.Many2many(
        "res.users", "angels_form_step_user_rel", "step_id", "user_id",
        string="People", readonly=True,
    )
    approved_by_ids = fields.Many2many(
        "res.users", "angels_form_step_approved_rel", "step_id", "user_id",
        string="Approved By", readonly=True,
    )
    decided_by_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    date_done = fields.Datetime(string="Done On", readonly=True)
    comment = fields.Text(readonly=True)

    def _remaining(self):
        self.ensure_one()
        return self.user_ids - self.approved_by_ids

    def _can_decide(self, user):
        self.ensure_one()
        return self.state == "pending" and user in self._remaining()

    def _activate(self):
        self.ensure_one()
        self.sudo().write({"state": "pending"})
        submission = self.submission_id.sudo()
        submission.message_subscribe(partner_ids=self.user_ids.partner_id.ids)
        for user in self.user_ids:
            submission.activity_schedule(
                "angels_forms.mail_activity_form_review",
                summary=_("Review %(request)s", request=submission.display_name),
                user_id=user.id,
            )

    def _notify(self, body):
        self.ensure_one()
        submission = self.submission_id.sudo()
        submission.message_subscribe(partner_ids=self.user_ids.partner_id.ids)
        submission.message_post(
            body=body,
            partner_ids=self.user_ids.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().write({"state": "notified", "date_done": fields.Datetime.now()})

    def _decide(self, decision, comment=False):
        self.ensure_one()
        user = self.env.user
        submission = self.submission_id
        if submission.state != "pending" or self.state != "pending":
            raise UserError(_("This step is no longer waiting for a decision."))
        if not self._can_decide(user):
            raise AccessError(_("You are not a reviewer of the step %(step)s.", step=self.name))
        if not submission.form_id.allow_self_approval and submission.user_id == user:
            raise UserError(_("You cannot approve or reject your own request."))
        if decision == "reject" and not (comment or "").strip():
            raise UserError(_("Give a reason for the rejection."))

        self._close_activities(user, comment)
        if decision == "reject":
            self.sudo().write({
                "state": "rejected", "decided_by_id": user.id,
                "date_done": fields.Datetime.now(), "comment": comment,
            })
            submission.sudo().message_post(
                body=Markup("<p>%s</p><p>%s</p>") % (
                    _("%(user)s rejected the step %(step)s.", user=user.name, step=self.name), comment,
                ),
                subtype_xmlid="mail.mt_note",
            )
            submission._finish("rejected")
            return True

        self.sudo().write({"approved_by_ids": [fields.Command.link(user.id)], "comment": comment or self.comment})
        submission.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(user)s approved the step %(step)s.", user=user.name, step=self.name)
            + (Markup("<p>%s</p>") % comment if comment else ""),
            subtype_xmlid="mail.mt_note",
        )
        if self.approval_rule == "any" or not self._remaining():
            self.sudo().write({"state": "approved", "decided_by_id": user.id, "date_done": fields.Datetime.now()})
            self._close_activities()
            submission._advance()
        return True

    def _close_activities(self, user=None, comment=False):
        activity_type = self.env.ref("angels_forms.mail_activity_form_review")
        activities = self.submission_id.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and (not user or a.user_id == user)
        )
        if user:
            activities.action_feedback(feedback=comment or False)
        else:
            activities.unlink()
