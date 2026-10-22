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
    current_step_id = fields.Many2one(
        "angels.form.step", string="Current Step", compute="_compute_current_step", store=True,
    )
    answers_html = fields.Html(string="Answers Summary", compute="_compute_answers_html", sanitize=False)
    is_my_turn = fields.Boolean(
        string="Waiting for Me", compute="_compute_is_my_turn", search="_search_is_my_turn",
    )
    can_cancel = fields.Boolean(compute="_compute_permissions")
    can_edit = fields.Boolean(compute="_compute_permissions")

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

    @api.depends("answer_ids", "form_id.field_ids")
    def _compute_answers_html(self):
        for submission in self:
            submission.answers_html = submission._render_answers()

    def _render_answers(self):
        self.ensure_one()
        answers = {answer.field_id: answer for answer in self.answer_ids}
        visible, _values = self.form_id._visible_values(self._answer_values())
        # Questions archived after the request was filled are still shown.
        questions = (visible | self.answer_ids.field_id).sorted(lambda f: f._position())
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
            rows.append(Markup('<tr><td class="o_af_label">%s</td><td>%s</td></tr>') % (field.name, value))
        if not rows:
            return False
        return Markup('<table class="table table-sm o_af_answers"><tbody>%s</tbody></table>') % Markup("").join(rows)

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------

    def _answer_values(self):
        self.ensure_one()
        return {answer.field_id.id: answer._get_value() for answer in self.sudo().answer_ids}

    def _answers_to_client(self):
        self.ensure_one()
        return {str(answer.field_id.id): answer._to_client() for answer in self.sudo().answer_ids}

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

    def _set_answers(self, raw_values):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only draft requests can be changed."))
        form = self.form_id
        raw_values = dict(raw_values or {})
        visible, values = form._visible_values(raw_values)
        # Uploads to hidden questions are not stored at all.
        for field in visible.filtered(lambda f: f.field_type == "file"):
            values[field.id] = self._store_files(raw_values.get(str(field.id))) or False
        Answer = self.env["angels.form.answer"].sudo()
        existing = {answer.field_id: answer for answer in self.sudo().answer_ids}
        for field in form.field_ids.filtered(lambda f: f.field_type != "section"):
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
        submission._set_answers(values)
        if submit:
            submission._submit()
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
        missing = visible.filtered(
            lambda f: f.required and f.field_type != "section" and not is_set(values.get(f.id))
        )
        if missing:
            raise UserError(_("Please answer: %(fields)s", fields=", ".join(missing.mapped("name"))))

        step_vals = []
        for rule in self.form_id.rule_ids.filtered(lambda r: r._applies(values)):
            recipients = rule._get_recipients(values)
            if not recipients:
                if rule.rule_type == "approve":
                    raise UserError(_("Nobody can approve the step %(step)s.", step=rule.name))
                continue
            step_vals.append({
                "submission_id": self.id,
                "rule_id": rule.id,
                "sequence": rule.sequence,
                "name": rule.name,
                "step_type": rule.rule_type,
                "approval_rule": rule.approval_rule,
                "user_ids": [fields.Command.set(recipients.ids)],
            })
        steps = self.env["angels.form.step"].sudo().create(step_vals)
        self.sudo().write({
            "name": self.env["ir.sequence"].sudo().next_by_code("angels.form.submission") or "/",
            "state": "pending",
            "date_submitted": fields.Datetime.now(),
        })
        self.sudo().message_subscribe(partner_ids=self.user_id.partner_id.ids)
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % _("Request sent by %(user)s.", user=self.user_id.name),
            subtype_xmlid="mail.mt_note",
        )
        for step in steps.filtered(lambda s: s.step_type == "notify_submit"):
            step._notify(Markup("<p>%s</p>") % _(
                "New request %(request)s from %(user)s.", request=self.display_name, user=self.user_id.name,
            ))
        self._advance()
        return True

    def _advance(self):
        """Open the next approval step, or approve the request when none is left."""
        self.ensure_one()
        step = self.step_ids.filtered(
            lambda s: s.step_type == "approve" and s.state == "waiting"
        ).sorted("sequence")[:1]
        if step:
            step._activate()
        else:
            self._finish("approved")

    def _finish(self, state):
        self.ensure_one()
        self.sudo().write({"state": state, "date_done": fields.Datetime.now()})
        waiting = self.step_ids.filtered(lambda s: s.state == "waiting")
        to_notify = waiting.filtered(lambda s: s.step_type == "notify_done") if state == "approved" else waiting.browse()
        (waiting - to_notify).sudo().write({"state": "skipped"})
        self.step_ids._close_activities()
        if state == "approved":
            body = _("The request %(request)s was approved.", request=self.display_name)
        else:
            body = _("The request %(request)s was rejected.", request=self.display_name)
        for step in to_notify:
            step._notify(Markup("<p>%s</p>") % body)
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % body,
            partner_ids=self.user_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )

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
        return {
            "type": "ir.actions.client",
            "tag": "angels_forms_fill",
            "name": self.form_id.name,
            "context": {"form_id": self.form_id.id, "submission_id": self.id},
        }

    def action_cancel(self):
        for submission in self:
            if not submission.can_cancel:
                raise AccessError(_("Only the requester or an administrator can cancel %(name)s.",
                                    name=submission.display_name))
            submission.sudo().write({"state": "cancelled", "date_done": fields.Datetime.now()})
            submission.step_ids.filtered(lambda s: s.state in ("waiting", "pending")).sudo().write(
                {"state": "skipped"}
            )
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
        if any(submission.state != "draft" for submission in self):
            raise UserError(_("Only draft requests can be deleted. Cancel the others instead."))
