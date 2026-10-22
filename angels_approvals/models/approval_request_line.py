from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

BATCH_SIZE = 200


class AngelsApprovalRequestLine(models.Model):
    _name = "angels.approval.request.line"
    _description = "Approval Request Step"
    _order = "request_id, sequence, id"

    request_id = fields.Many2one(
        "angels.approval.request", required=True, ondelete="cascade", index=True, readonly=True
    )
    step_id = fields.Many2one(
        "angels.approval.step", string="Flow Step", ondelete="set null", readonly=True
    )
    sequence = fields.Integer(readonly=True)
    name = fields.Char(string="Step", required=True, readonly=True)
    approval_rule = fields.Selection(
        [("any", "One approver is enough"), ("all", "Every approver must approve")],
        string="Rule", required=True, readonly=True,
    )
    state = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("pending", "To Approve"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("skipped", "Skipped"),
        ],
        required=True, default="waiting", readonly=True, index=True,
    )
    approver_ids = fields.Many2many(
        "res.users", "angels_approval_line_approver_rel", "line_id", "user_id",
        string="Approvers", readonly=True,
    )
    actor_ids = fields.Many2many(
        "res.users", "angels_approval_line_actor_rel", "line_id", "user_id",
        string="Approvers and Delegates", readonly=True,
        help="Approvers plus the users they delegated to. Grants read access to the request.",
    )
    decision_ids = fields.One2many("angels.approval.decision", "line_id", string="Decisions")
    date_start = fields.Datetime(string="Started On", readonly=True)
    deadline = fields.Date(readonly=True)
    last_reminder = fields.Date(readonly=True)
    escalated = fields.Boolean(readonly=True)

    # ------------------------------------------------------------------
    # Approvers
    # ------------------------------------------------------------------

    def _remaining_approvers(self):
        self.ensure_one()
        return self.approver_ids - self.decision_ids.on_behalf_of_id

    def _principals_for(self, user):
        """Approvers of this step that ``user`` may decide for right now."""
        self.ensure_one()
        if self.state != "pending":
            return self.env["res.users"]
        remaining = self._remaining_approvers()
        delegators = self.env["angels.approval.delegation"]._delegators_of(user)
        return remaining & (user | delegators)

    def _refresh_actors(self):
        Delegation = self.env["angels.approval.delegation"]
        for line in self:
            actors = line.approver_ids | Delegation._delegates_of(line.approver_ids)
            line.sudo().actor_ids = [fields.Command.link(u.id) for u in actors]

    def _activate(self):
        self.ensure_one()
        request = self.request_id
        record = request._get_record()
        approvers = self.step_id._get_approvers(record) if self.step_id and record else self.approver_ids
        if not approvers:
            raise UserError(_("The step %(step)s has no approvers.", step=self.name))
        days = self.step_id.deadline_days
        today = fields.Date.context_today(self)
        self.sudo().write({
            "state": "pending",
            "approver_ids": [fields.Command.set(approvers.ids)],
            "date_start": fields.Datetime.now(),
            "deadline": today + timedelta(days=days) if days else False,
        })
        self._refresh_actors()
        self._notify_users(self.approver_ids)

    def _notify_users(self, approvers):
        """Schedule an activity for each approver, or for their delegate."""
        request = self.request_id.sudo()
        Delegation = self.env["angels.approval.delegation"]
        for approver in approvers:
            assignee = Delegation._delegates_of(approver)[:1] or approver
            request.activity_schedule(
                "angels_approvals.mail_activity_approval",
                date_deadline=self.deadline or fields.Date.context_today(self),
                summary=_("Approve %(record)s", record=request.res_name),
                note=request.note or "",
                user_id=assignee.id,
            )

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def _decide(self, decision, comment=False):
        self.ensure_one()
        user = self.env.user
        request = self.request_id
        if request.state != "pending" or self.state != "pending":
            raise UserError(_("This step is no longer waiting for a decision."))
        principals = self._principals_for(user)
        if not principals:
            raise AccessError(_("You are not an approver of the step %(step)s.", step=self.name))
        if not request.flow_id.allow_self_approval and request.requested_by_id in (user | principals):
            raise UserError(_("You cannot approve or reject your own request."))
        if decision == "reject" and not (comment or "").strip():
            raise UserError(_("Give a reason for the rejection."))

        self.env["angels.approval.decision"].sudo().create([
            {
                "line_id": self.id,
                "user_id": user.id,
                "on_behalf_of_id": principal.id,
                "decision": decision,
                "comment": comment,
            }
            for principal in principals
        ])
        self._close_my_activities(user, comment)
        if decision == "reject":
            self.sudo().state = "rejected"
            request._finish("rejected")
        elif self.approval_rule == "any" or not self._remaining_approvers():
            self.sudo().state = "approved"
            request._clear_activities()
            request._advance()
        return True

    def _close_my_activities(self, user, comment):
        activity_type = self.env.ref("angels_approvals.mail_activity_approval")
        activities = self.request_id.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == user
        )
        activities.action_feedback(feedback=comment or False)

    # ------------------------------------------------------------------
    # Reminders and escalation
    # ------------------------------------------------------------------

    @api.model
    def _overdue_domain(self, today):
        return [
            ("state", "=", "pending"),
            ("request_id.state", "=", "pending"),
            ("deadline", "!=", False),
            ("deadline", "<", today),
            "|", ("last_reminder", "=", False), ("last_reminder", "<", today),
        ]

    @api.model
    def _process_overdue(self, limit=BATCH_SIZE):
        """Remind or escalate one batch of overdue steps. Returns the count."""
        today = fields.Date.context_today(self)
        lines = self.search(self._overdue_domain(today), order="deadline, id", limit=limit)
        for line in lines:
            line._remind(today)
        return len(lines)

    @api.model
    def _cron_remind_overdue(self):
        Cron = self.env["ir.cron"]
        while processed := self._process_overdue():
            remaining = self.search_count(self._overdue_domain(fields.Date.context_today(self)))
            if not Cron._commit_progress(processed, remaining=remaining) or not remaining:
                break

    def _remind(self, today):
        self.ensure_one()
        step = self.step_id
        escalate = step.escalation_user_id
        if escalate and not self.escalated and escalate not in self.approver_ids:
            self.sudo().write({
                "approver_ids": [fields.Command.link(escalate.id)],
                "escalated": True,
            })
            self._refresh_actors()
            self._notify_users(escalate)
            body = _("The step %(step)s is overdue and was escalated to %(user)s.",
                     step=self.name, user=escalate.name)
        else:
            body = _("Reminder: the step %(step)s is overdue.", step=self.name)
        actors = self.actor_ids - self.decision_ids.user_id
        self.request_id.sudo().message_post(
            body=Markup("<p>%s</p>") % body,
            partner_ids=actors.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().last_reminder = today
