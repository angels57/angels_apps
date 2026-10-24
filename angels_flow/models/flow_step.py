from markupsafe import Markup

from odoo import _, api, fields, models
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
            ("expired", "Expired"),
            ("skipped", "Skipped"),
        ],
        required=True, default="pending", readonly=True, index=True,
    )
    decided_by_id = fields.Many2one("res.users", string="Decided By", readonly=True)
    date_deadline = fields.Datetime(string="Deadline", readonly=True, index=True)
    is_late = fields.Boolean(string="Late", readonly=True,
                             help="The deadline passed: the reminder or the escalation was done.")
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
        self._flow_schedule(self.user_ids, summary)

    def _flow_schedule(self, users, summary):
        document = self._flow_doc().sudo()
        activity_type = document._flow_activity_type()
        deadline = {"date_deadline": fields.Date.to_date(self.date_deadline)} if self.date_deadline else {}
        for user in users:
            document.activity_schedule(activity_type_id=activity_type.id, summary=summary, user_id=user.id,
                                       **deadline)

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

    @api.model
    def _flow_stats(self, nodes):
        """How long the people of each step take: {node id: {count, hours}} over finished steps."""
        stats = {}
        done = self.sudo().search([
            ("node_id", "in", nodes.ids), ("state", "in", ("approved", "done", "rejected", "expired")),
            ("date_done", "!=", False),
        ], order="id desc", limit=5000)
        for step in done:
            item = stats.setdefault(step.node_id.id, {"count": 0, "total": 0.0})
            item["count"] += 1
            item["total"] += (step.date_done - step.create_date).total_seconds() / 3600
        return {node_id: {"count": item["count"], "hours": round(item["total"] / item["count"], 1)}
                for node_id, item in stats.items()}

    # ------------------------------------------------------------------
    # Deadlines
    # ------------------------------------------------------------------

    @api.model
    def _flow_check_deadlines(self):
        """Steps of this model whose deadline passed: remind, escalate or expire them."""
        late = self.sudo().search([
            ("state", "=", "pending"), ("is_late", "=", False),
            ("date_deadline", "!=", False), ("date_deadline", "<=", fields.Datetime.now()),
        ])
        for step in late:
            document = step._flow_doc()
            if document.state != "pending":
                continue
            try:
                with self.env.cr.savepoint():
                    step._flow_on_deadline()
            except UserError as error:
                # The step after "Expired" could not run: the document says why.
                document.sudo().message_post(body=Markup("<p>%s</p>") % str(error), subtype_xmlid="mail.mt_note")

    def _flow_on_deadline(self):
        self.ensure_one()
        node = self.node_id
        document = self._flow_doc().sudo()
        self.write({"is_late": True})
        rule = node.on_deadline or "remind"
        if rule == "escalate" and node.escalate_user_id:
            user = node.escalate_user_id
            self.write({"user_ids": [fields.Command.link(user.id)]})
            document.message_subscribe(partner_ids=user.partner_id.ids)
            self._flow_schedule(user, _("Late: %(request)s", request=document.display_name))
            body = _("%(step)s is late: it goes to %(user)s too.", step=self.name, user=user.name)
            partners = (self.user_ids | user).partner_id
        elif rule == "expire":
            self.write({"state": "expired", "date_done": fields.Datetime.now()})
            self._flow_close_activities()
            document.message_post(
                body=Markup("<p>%s</p>") % _("%(step)s expired: nobody acted in time.", step=self.name),
                subtype_xmlid="mail.mt_note",
            )
            if node.expired_id:
                document._flow_run(node.expired_id)
            else:
                document._flow_finish("rejected")
            return
        else:
            body = _("%(step)s is late: please act on it.", step=self.name)
            partners = self._remaining().partner_id
        document.message_post(body=Markup("<p>%s</p>") % body, partner_ids=partners.ids,
                              subtype_xmlid="mail.mt_comment")
