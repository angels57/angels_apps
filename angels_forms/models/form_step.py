from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

from .form_condition import is_set

STEP_TYPES = [
    ("approve", "Approval"),
    ("task", "Task"),
    ("notify", "Notification"),
]


class AngelsFormStep(models.Model):
    """One flow step reached by one request: an approval, a task or a notification."""

    _name = "angels.form.step"
    _description = "Form Request Step"
    _order = "submission_id, sequence, id"

    submission_id = fields.Many2one(
        "angels.form.submission", required=True, ondelete="cascade", index=True, readonly=True,
    )
    node_id = fields.Many2one("angels.form.node", string="Flow Step", ondelete="set null", readonly=True)
    sequence = fields.Integer(readonly=True)
    name = fields.Char(string="Step", required=True, readonly=True)
    step_type = fields.Selection(STEP_TYPES, string="Action", required=True, readonly=True)
    approval_rule = fields.Selection(
        [("any", "One person is enough"), ("all", "Everyone must approve")],
        string="Rule", required=True, default="any", readonly=True,
    )
    state = fields.Selection(
        [
            ("pending", "To Do"),
            ("approved", "Approved"),
            ("done", "Done"),
            ("rejected", "Rejected"),
            ("notified", "Informed"),
            ("skipped", "Skipped"),
        ],
        required=True, default="pending", readonly=True, index=True,
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
        return self.state == "pending" and self.step_type != "notify" and user in self._remaining()

    def _fields_to_fill(self):
        self.ensure_one()
        return self.node_id.field_ids if self.node_id else self.env["angels.form.field"]

    def _activate(self):
        self.ensure_one()
        submission = self.submission_id.sudo()
        submission.message_subscribe(partner_ids=self.user_ids.partner_id.ids)
        if self.step_type == "task":
            summary = _("Complete %(request)s", request=submission.display_name)
        else:
            summary = _("Review %(request)s", request=submission.display_name)
        for user in self.user_ids:
            submission.activity_schedule(
                "angels_forms.mail_activity_form_review", summary=summary, user_id=user.id,
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

    def _decide(self, decision, comment=False):
        """``decision`` is "approve" (also "done" for a task) or "reject"."""
        self.ensure_one()
        user = self.env.user
        submission = self.submission_id
        if submission.state != "pending" or self.state != "pending":
            raise UserError(_("This step is no longer waiting for a decision."))
        if not self._can_decide(user):
            raise AccessError(_("You are not a reviewer of the step %(step)s.", step=self.name))
        if not submission.form_id.allow_self_approval and submission.user_id == user:
            raise UserError(_("You cannot approve or reject your own request."))
        if decision == "reject":
            if self.step_type != "approve":
                raise UserError(_("A task cannot be rejected."))
            if not (comment or "").strip():
                raise UserError(_("Give a reason for the rejection."))
        else:
            self._check_filled()

        self._close_activities(user, comment)
        node = self.node_id
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
            if node.reject_id:
                submission._run(node.reject_id)
            else:
                submission._finish("rejected")
            return True

        done_state = "done" if self.step_type == "task" else "approved"
        if self.step_type == "task":
            message = _("%(user)s completed the step %(step)s.", user=user.name, step=self.name)
        else:
            message = _("%(user)s approved the step %(step)s.", user=user.name, step=self.name)
        self.sudo().write({"approved_by_ids": [fields.Command.link(user.id)], "comment": comment or self.comment})
        submission.sudo().message_post(
            body=Markup("<p>%s</p>") % message + (Markup("<p>%s</p>") % comment if comment else ""),
            subtype_xmlid="mail.mt_note",
        )
        if self.step_type == "task" or self.approval_rule == "any" or not self._remaining():
            self.sudo().write({"state": done_state, "decided_by_id": user.id, "date_done": fields.Datetime.now()})
            self._close_activities()
            submission._run(node.next_id)
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
