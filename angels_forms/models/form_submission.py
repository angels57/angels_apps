from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .form_condition import is_set

STATES = [
    ("draft", "Draft"),
    ("pending", "In Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]
TITLE_LENGTH = 80


class AngelsFormSubmission(models.Model):
    _name = "angels.form.submission"
    _description = "Form Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    # Reviewers only read the request; they still discuss it in the chatter.
    _mail_post_access = "read"

    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="/")
    form_id = fields.Many2one("angels.form", required=True, readonly=True, ondelete="restrict", index=True)
    title = fields.Char(compute="_compute_title", store=True)
    user_id = fields.Many2one(
        "res.users", string="Requested By", required=True, readonly=True, index=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one("res.company", readonly=True, index=True)
    state = fields.Selection(STATES, required=True, default="draft", readonly=True, tracking=True, index=True)
    date_submitted = fields.Datetime(string="Sent On", readonly=True)
    date_done = fields.Datetime(string="Decided On", readonly=True)
    answer_ids = fields.One2many("angels.form.answer", "submission_id", string="Answers")
    step_ids = fields.One2many("angels.form.step", "submission_id", string="Steps")
    current_step_type = fields.Selection(related="current_step_id.step_type", string="Current Step Type")
    current_step_id = fields.Many2one(
        "angels.form.step", string="Current Step", compute="_compute_current_step", store=True,
    )
    answers_html = fields.Html(string="Answers Summary", compute="_compute_answers_html", sanitize=False)
    is_my_turn = fields.Boolean(
        string="Waiting for Me", compute="_compute_is_my_turn", search="_search_is_my_turn",
    )
    can_cancel = fields.Boolean(compute="_compute_permissions")
    can_edit = fields.Boolean(compute="_compute_permissions")
    link_ids = fields.One2many("angels.form.link", "submission_id", string="Created Records", readonly=True)
    link_count = fields.Integer(compute="_compute_link_count")

    @api.depends("form_id", "answer_ids.display_value", "form_id.title_field_id")
    def _compute_title(self):
        for submission in self:
            title_field = submission.form_id.title_field_id
            answer = submission.answer_ids.filtered(lambda a: a.field_id == title_field)[:1]
            title = answer.display_value if title_field and answer else ""
            submission.title = (title or submission.form_id.name or "")[:TITLE_LENGTH]

    @api.depends("name", "title", "state")
    def _compute_display_name(self):
        for submission in self:
            name = submission.name if submission.name != "/" else _("Draft")
            submission.display_name = f"{name} - {submission.title}" if submission.title else name

    @api.depends("step_ids.state")
    def _compute_current_step(self):
        for submission in self:
            submission.current_step_id = submission.step_ids.filtered(lambda s: s.state == "pending")[:1]

    @api.depends_context("uid")
    @api.depends("state", "current_step_id")
    def _compute_is_my_turn(self):
        user = self.env.user
        for submission in self:
            step = submission.sudo().current_step_id
            submission.is_my_turn = bool(submission.state == "pending" and step and step._can_decide(user))

    def _search_is_my_turn(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        user = self.env.user
        steps = self.env["angels.form.step"].sudo().search([
            ("state", "=", "pending"),
            ("submission_id.state", "=", "pending"),
            ("user_ids", "in", user.ids),
        ]).filtered(lambda s: s._can_decide(user))
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", steps.submission_id.ids)]

    @api.depends_context("uid")
    @api.depends("state", "user_id")
    def _compute_permissions(self):
        user = self.env.user
        is_manager = user.has_group("angels_forms.group_form_manager")
        for submission in self:
            mine = submission.user_id == user
            submission.can_edit = submission.state == "draft" and mine
            submission.can_cancel = submission.state in ("draft", "pending") and (mine or is_manager)

    @api.depends("link_ids")
    def _compute_link_count(self):
        for submission in self:
            submission.link_count = len(submission.link_ids)

    @api.depends("answer_ids", "step_ids", "form_id.field_ids")
    def _compute_answers_html(self):
        for submission in self:
            submission.answers_html = submission._render_answers()

    def _render_answers(self):
        self.ensure_one()
        answers = {answer.field_id: answer for answer in self.answer_ids}
        visible, _values = self.form_id._visible_values(self._answer_values())
        # Questions archived after the request was filled are still shown.
        questions = ((visible & self._reached_fields()) | self.answer_ids.field_id).sorted(
            lambda f: f._position()
        )
        rows = []
        for field in questions:
            if field.field_type == "section":
                rows.append(Markup('<tr><th colspan="2" class="o_af_section">%s</th></tr>') % field.name)
                continue
            answer = answers.get(field)
            if answer:
                value = answer.display_value
            elif field.field_type == "boolean":
                value = _("No")
            else:
                value = "-"
            if field.field_type == "text" and answer:
                value = Markup("<br/>").join(escape(line) for line in value.splitlines())
            label = Markup("%s") % field.name
            if field.node_id:
                label += Markup(' <span class="o_af_stage o_af_stage_%s">%s</span>') % (
                    field.node_id.color % 12, field.node_id.name,
                )
            rows.append(Markup('<tr><td class="o_af_label">%s</td><td>%s</td></tr>') % (label, value))
        if not rows:
            return False
        return Markup('<table class="table table-sm o_af_answers"><tbody>%s</tbody></table>') % Markup("").join(rows)

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------

    def _answer_values(self):
        self.ensure_one()
        return {answer.field_id.id: answer._get_value() for answer in self.sudo().answer_ids}

    def _answer_text(self, field):
        """The answer to ``field`` as it reads in the summary, or an empty string."""
        self.ensure_one()
        answer = self.sudo().answer_ids.filtered(lambda a: a.field_id == field)[:1]
        return answer._format() if answer else ""

    def _answers_to_client(self):
        self.ensure_one()
        return {str(answer.field_id.id): answer._to_client() for answer in self.sudo().answer_ids}

    def _reached_fields(self):
        """Questions of the requester and of the steps this request already reached."""
        self.ensure_one()
        nodes = self.sudo().step_ids.node_id
        return self.form_id.field_ids.filtered(lambda f: not f.node_id or f.node_id in nodes)

    def _editable_fields(self):
        """Questions the current user may answer now."""
        self.ensure_one()
        if self.can_edit:
            return self.form_id._requester_fields()
        if self.is_my_turn:
            return self.sudo().current_step_id._fields_to_fill().with_env(self.env)
        return self.env["angels.form.field"]

    def _store_files(self, items):
        """Attachment ids for a file question: keep this request's files, add new uploads."""
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()
        ids = []
        for item in items or []:
            if item.get("id"):
                attachment = Attachment.browse(int(item["id"])).exists()
                if attachment.res_model == self._name and attachment.res_id == self.id:
                    ids.append(attachment.id)
            elif item.get("data"):
                ids.append(Attachment.create({
                    "name": item.get("name") or _("File"),
                    "datas": item["data"],
                    "res_model": self._name,
                    "res_id": self.id,
                }).id)
        return ids

    def _set_answers(self, raw_values, editable):
        """Store the answers to the ``editable`` questions; the others stay as they are."""
        self.ensure_one()
        form = self.form_id
        raw_values = dict(raw_values or {})
        merged = self._answer_values()
        for field in editable:
            merged[field.id] = raw_values.get(str(field.id), raw_values.get(field.id))
        visible, values = form._visible_values(merged)
        # Uploads to hidden questions are not stored at all.
        for field in (visible & editable).filtered(lambda f: f.field_type == "file"):
            values[field.id] = self._store_files(merged.get(field.id)) or False
        Answer = self.env["angels.form.answer"].sudo()
        existing = {answer.field_id: answer for answer in self.sudo().answer_ids}
        for field in editable.filtered(lambda f: f.field_type != "section"):
            value = values.get(field.id, False)
            answer = existing.get(field, Answer)
            if not is_set(value):
                answer.unlink()
                continue
            vals = Answer._value_vals(field, value)
            if answer:
                answer.write(vals)
            else:
                Answer.create(dict(vals, submission_id=self.id, field_id=field.id))

    @api.model
    def save_from_filler(self, form_id, submission_id, values, submit=False):
        """Create or update a draft from the fill screen, and send it if asked."""
        if submission_id:
            submission = self.browse(submission_id)
            submission.check_access("read")
            if not submission.can_edit:
                raise UserError(_("Only the requester can change a draft request."))
        else:
            form = self.env["angels.form"].browse(form_id)
            if not form._can_submit():
                raise AccessError(_("You cannot fill the form %(form)s.", form=form.name))
            company = form.company_id or self.env.company
            submission = self.sudo().create({
                "form_id": form.id,
                "user_id": self.env.uid,
                "company_id": company.id,
            }).with_env(self.env)
        submission._set_answers(values, submission.form_id._requester_fields())
        if submit:
            submission._submit()
        return submission.id

    @api.model
    def save_step(self, submission_id, values, done=False, comment=False):
        """Answers of the current step, from the fill screen; ``done`` also approves it."""
        submission = self.browse(submission_id)
        submission.check_access("read")
        if not submission.is_my_turn:
            raise UserError(_("This request is not waiting for your decision."))
        step = submission.sudo().current_step_id.with_env(self.env)
        submission._set_answers(values, step._fields_to_fill())
        if done:
            step._decide("approve", comment)
        return submission.id

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def _submit(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("This request was already sent."))
        if not self.form_id._can_submit(self.user_id):
            raise UserError(_("The form %(form)s is not open for requests.", form=self.form_id.name))
        visible, values = self.form_id._visible_values(self._answer_values())
        missing = (visible & self.form_id._requester_fields()).filtered(
            lambda f: f.required and f.field_type != "section" and not is_set(values.get(f.id))
        )
        if missing:
            raise UserError(_("Please answer: %(fields)s", fields=", ".join(missing.mapped("name"))))
        resent = self.name != "/"
        self.sudo().write({
            "name": self.name if resent else (
                self.env["ir.sequence"].sudo().next_by_code("angels.form.submission") or "/"
            ),
            "state": "pending",
            "date_submitted": fields.Datetime.now(),
        })
        self._close_requester_activities()
        self.sudo().message_subscribe(partner_ids=self.user_id.partner_id.ids)
        if resent:
            body = _("Request corrected and sent again by %(user)s.", user=self.user_id.name)
        else:
            body = _("Request sent by %(user)s.", user=self.user_id.name)
        self.sudo().message_post(body=Markup("<p>%s</p>") % body, subtype_xmlid="mail.mt_note")
        self._run(self.form_id._start_node().next_id)
        return True

    def _run(self, node):
        """Walk the flow from ``node`` until a step waits for people, or the end.

        A missing link ends the flow: the request is approved.
        """
        self.ensure_one()
        values = self.form_id._visible_values(self._answer_values())[1]
        Step = self.env["angels.form.step"].sudo()
        seen = set()
        while node:
            if node.id in seen:
                raise UserError(_("The flow of %(form)s goes round in a circle at %(step)s.",
                                  form=self.form_id.name, step=node.name))
            seen.add(node.id)
            kind = node.node_type
            if kind == "start":
                node = node.next_id
            elif kind == "condition":
                node = node.yes_id if node._conditions_met(values) else node.no_id
            elif kind == "end":
                return self._finish(node.end_state or "approved")
            elif kind == "back":
                return self._send_back(node)
            elif kind == "record":
                node._create_record(self, values)
                node = node.next_id
            else:
                recipients = node._get_recipients(values)
                if not recipients:
                    if kind == "notify":
                        node = node.next_id
                        continue
                    raise UserError(_("Nobody can do the step %(step)s.", step=node.name))
                step = Step.create({
                    "submission_id": self.id,
                    "node_id": node.id,
                    "sequence": len(self.step_ids) + 1,
                    "name": node.name,
                    "step_type": kind,
                    "approval_rule": node.approval_rule or "any",
                    "user_ids": [fields.Command.set(recipients.ids)],
                })
                if kind == "notify":
                    step._notify(Markup("<p>%s</p>") % _(
                        "%(step)s: request %(request)s from %(user)s.",
                        step=node.name, request=self.display_name, user=self.user_id.name,
                    ))
                    node = node.next_id
                    continue
                step._activate()
                return True
        return self._finish("approved")

    def _send_back(self, node):
        """Reopen the request so the requester corrects it and sends it again."""
        self.ensure_one()
        self.sudo().write({"state": "draft"})
        self.step_ids._close_activities()
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(step)s: the request goes back to %(user)s to be corrected.",
                                         step=node.name, user=self.user_id.name),
            partner_ids=self.user_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().activity_schedule(
            "angels_forms.mail_activity_form_review",
            summary=_("Correct %(request)s", request=self.display_name),
            user_id=self.user_id.id,
        )
        return True

    def _close_requester_activities(self):
        activity_type = self.env.ref("angels_forms.mail_activity_form_review")
        self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == self.user_id
        ).unlink()

    def _finish(self, state):
        self.ensure_one()
        self.sudo().write({"state": state, "date_done": fields.Datetime.now()})
        self.step_ids._close_activities()
        if state == "approved":
            body = _("The request %(request)s was approved.", request=self.display_name)
        else:
            body = _("The request %(request)s was rejected.", request=self.display_name)
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % body,
            partner_ids=self.user_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        return True

    def action_submit(self):
        for submission in self:
            if not submission.can_edit:
                raise UserError(_("Only the requester can send a draft request."))
            submission._submit()
        return True

    def action_edit(self):
        self.ensure_one()
        if not self.can_edit:
            raise UserError(_("Only the requester can change a draft request."))
        return self._fill_action()

    def _fill_action(self):
        return {
            "type": "ir.actions.client",
            "tag": "angels_forms_fill",
            "name": self.form_id.name,
            "context": {"form_id": self.form_id.id, "submission_id": self.id},
        }

    def action_view_links(self):
        self.ensure_one()
        if len(self.link_ids) == 1:
            return self.link_ids.action_open()
        return {
            "type": "ir.actions.act_window",
            "name": _("Created Records"),
            "res_model": "angels.form.link",
            "views": [[False, "list"]],
            "domain": [("submission_id", "=", self.id)],
        }

    def action_cancel(self):
        for submission in self:
            if not submission.can_cancel:
                raise AccessError(_("Only the requester or an administrator can cancel %(name)s.",
                                    name=submission.display_name))
            submission.sudo().write({"state": "cancelled", "date_done": fields.Datetime.now()})
            submission.step_ids.filtered(lambda s: s.state == "pending").sudo().write({"state": "skipped"})
            submission.step_ids._close_activities()
            submission.sudo().message_post(
                body=Markup("<p>%s</p>") % _("Request cancelled by %(user)s.", user=self.env.user.name),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def _open_decision_wizard(self, decision):
        self.ensure_one()
        if not self.is_my_turn:
            raise UserError(_("This request is not waiting for your decision."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Approve") if decision == "approve" else _("Reject"),
            "res_model": "angels.form.decision.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_submission_id": self.id, "default_decision": decision},
        }

    def action_approve(self):
        """Steps with questions to fill open the fill screen; the others a short dialog."""
        self.ensure_one()
        if self.is_my_turn and self.sudo().current_step_id._fields_to_fill():
            return self._fill_action()
        return self._open_decision_wizard("approve")

    def action_reject(self):
        return self._open_decision_wizard("reject")

    def write(self, vals):
        if not self.env.su and {"state", "form_id", "user_id", "name"} & set(vals):
            self.check_access("write")
            raise UserError(_("Requests change only through their workflow."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_drafts(self):
        if any(submission.state != "draft" or submission.step_ids for submission in self):
            raise UserError(_("Only draft requests can be deleted. Cancel the others instead."))
