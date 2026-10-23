from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError

STEP_TYPES = [
    ("approve", "Approval"),
    ("task", "Task"),
    ("notify", "Notification"),
]


class AngelsFlowStepMixin(models.AbstractModel):
    """One flow step reached by one document: an approval, a task or a notification.

    The model that inherits it names its Many2one to the document
    (``_flow_document``) and declares ``node_id`` (the flow step), ``user_ids``
    (who must act) and ``approved_by_ids``.
    """

    _name = "angels.flow.step.mixin"
    _description = "Flow Document Step"
    _flow_document = None

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
    decided_by_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    date_done = fields.Datetime(string="Done On", readonly=True)
    comment = fields.Text(readonly=True)

    def _flow_doc(self):
        self.ensure_one()
        return self[self._flow_document]

    def _remaining(self):
        self.ensure_one()
        return self.user_ids - self.approved_by_ids

    def _can_decide(self, user):
        self.ensure_one()
        return self.state == "pending" and self.step_type != "notify" and user in self._remaining()

    def _activate(self):
        self.ensure_one()
        document = self._flow_doc().sudo()
        document.message_subscribe(partner_ids=self.user_ids.partner_id.ids)
        if self.step_type == "task":
            summary = _("Complete %(request)s", request=document.display_name)
        else:
            summary = _("Review %(request)s", request=document.display_name)
        activity_type = document._flow_activity_type()
        for user in self.user_ids:
            document.activity_schedule(activity_type_id=activity_type.id, summary=summary, user_id=user.id)

    def _notify(self, body):
        self.ensure_one()
        document = self._flow_doc().sudo()
        document.message_subscribe(partner_ids=self.user_ids.partner_id.ids)
        document.message_post(
            body=body,
            partner_ids=self.user_ids.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().write({"state": "notified", "date_done": fields.Datetime.now()})

    def _flow_before_done(self):
        """Raise if the step cannot be approved or completed yet."""
        self.ensure_one()

    def _decide(self, decision, comment=False):
        """``decision`` is "approve" (also "done" for a task) or "reject"."""
        self.ensure_one()
        user = self.env.user
        document = self._flow_doc()
        if document.state != "pending" or self.state != "pending":
            raise UserError(_("This step is no longer waiting for a decision."))
        if not self._can_decide(user):
            raise AccessError(_("You are not a reviewer of the step %(step)s.", step=self.name))
        if not document._flow_allow_self_approval() and document._flow_requester() == user:
            raise UserError(_("You cannot approve or reject your own request."))
        if decision == "reject":
            if self.step_type != "approve":
                raise UserError(_("A task cannot be rejected."))
            if not (comment or "").strip():
                raise UserError(_("Give a reason for the rejection."))
        else:
            self._flow_before_done()

        self._flow_close_activities(user, comment)
        node = self.node_id
        if decision == "reject":
            self.sudo().write({
                "state": "rejected", "decided_by_id": user.id,
                "date_done": fields.Datetime.now(), "comment": comment,
            })
            document.sudo().message_post(
                body=Markup("<p>%s</p><p>%s</p>") % (
                    _("%(user)s rejected the step %(step)s.", user=user.name, step=self.name), comment,
                ),
                subtype_xmlid="mail.mt_note",
            )
            if node.reject_id:
                document._flow_run(node.reject_id)
            else:
                document._flow_finish("rejected")
            return True

        done_state = "done" if self.step_type == "task" else "approved"
        if self.step_type == "task":
            message = _("%(user)s completed the step %(step)s.", user=user.name, step=self.name)
        else:
            message = _("%(user)s approved the step %(step)s.", user=user.name, step=self.name)
        self.sudo().write({"approved_by_ids": [fields.Command.link(user.id)], "comment": comment or self.comment})
        document.sudo().message_post(
            body=Markup("<p>%s</p>") % message + (Markup("<p>%s</p>") % comment if comment else ""),
            subtype_xmlid="mail.mt_note",
        )
        if self.step_type == "task" or self.approval_rule == "any" or not self._remaining():
            self.sudo().write({"state": done_state, "decided_by_id": user.id, "date_done": fields.Datetime.now()})
            self._flow_close_activities()
            document._flow_run(node.next_id)
        return True

    def _flow_close_activities(self, user=None, comment=False):
        """Close the activities of these steps: one person's with feedback, or all of them."""
        for document in self.mapped(self._flow_document):
            activity_type = document._flow_activity_type()
            activities = document.sudo().activity_ids.filtered(
                lambda a: a.activity_type_id == activity_type and (not user or a.user_id == user)
            )
            if user:
                activities.action_feedback(feedback=comment or False)
            else:
                activities.unlink()
