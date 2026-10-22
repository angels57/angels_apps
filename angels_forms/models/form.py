from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .form_condition import OPERATORS_BY_TYPE

SUBMISSION_MODEL = "angels.form.submission"
FIELD_KEYS = ("name", "field_type", "required", "help", "placeholder", "width", "condition_match")
RULE_KEYS = ("name", "rule_type", "assign_type", "approval_rule", "condition_match")


class AngelsForm(models.Model):
    _name = "angels.form"
    _description = "Form"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    published = fields.Boolean(help="Published forms appear under New Request.")
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    icon = fields.Char(default="fa-file-text-o", help="Font Awesome icon, for example fa-plane.")
    color = fields.Integer()
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        help="Leave empty to use the form in every company.",
    )
    field_ids = fields.One2many("angels.form.field", "form_id", string="Fields", copy=True)
    rule_ids = fields.One2many("angels.form.rule", "form_id", string="Routing")
    title_field_id = fields.Many2one(
        "angels.form.field",
        string="Title From",
        domain="[('form_id', '=', id), ('field_type', 'in', ('char', 'selection', 'date', 'partner', 'user'))]",
        help="The answer to this question names each request, for example the destination of a trip.",
    )
    group_ids = fields.Many2many(
        "res.groups",
        string="Allowed Groups",
        help="Groups allowed to fill the form. Empty means every forms user.",
    )
    allow_self_approval = fields.Boolean(
        help="Let the requester approve a step where they are an approver.",
    )
    can_fill = fields.Boolean(compute="_compute_can_fill", search="_search_can_fill")
    submission_ids = fields.One2many(SUBMISSION_MODEL, "form_id", string="Requests")
    submission_count = fields.Integer(compute="_compute_submission_count")
    field_count = fields.Integer(compute="_compute_counts")
    rule_count = fields.Integer(compute="_compute_counts")

    def _compute_submission_count(self):
        counts = dict(
            self.env[SUBMISSION_MODEL]._read_group(
                [("form_id", "in", self.ids), ("state", "!=", "draft")], ["form_id"], ["__count"]
            )
        )
        for form in self:
            form.submission_count = counts.get(form, 0)

    @api.depends_context("uid")
    @api.depends("published", "group_ids")
    def _compute_can_fill(self):
        for form in self:
            form.can_fill = form._can_submit()

    def _search_can_fill(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        forms = self.search([
            ("published", "=", True),
            "|", ("group_ids", "=", False), ("group_ids", "in", self.env.user.all_group_ids.ids),
        ])
        positive = (operator == "=") == value
        return [("id", "in" if positive else "not in", forms.ids)]

    @api.depends("field_ids", "rule_ids")
    def _compute_counts(self):
        for form in self:
            form.field_count = len(form.field_ids.filtered(lambda f: f.field_type != "section"))
            form.rule_count = len(form.rule_ids)

    @api.constrains("title_field_id")
    def _check_title_field(self):
        for form in self:
            if form.title_field_id and form.title_field_id.form_id != form:
                raise ValidationError(_("The title must come from a question of the same form."))

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for form, vals in zip(self, vals_list):
            vals.setdefault("name", _("%s (copy)", form.name))
            vals["published"] = False
            vals.pop("title_field_id", None)
        return vals_list

    def copy(self, default=None):
        # Conditions point at fields of the same form: rebuild them on the copy.
        new_forms = super().copy(default=default)
        for form, new in zip(self, new_forms):
            mapping = dict(zip(form.field_ids, new.field_ids))
            for field, new_field in mapping.items():
                new_field.condition_ids = [
                    fields.Command.create({
                        "source_field_id": mapping[c.source_field_id].id,
                        "operator": c.operator,
                        "value": c.value,
                    })
                    for c in field.condition_ids
                ]
            for rule in form.rule_ids:
                rule.copy({
                    "form_id": new.id,
                    "user_field_id": mapping.get(rule.user_field_id, rule.user_field_id).id,
                    "condition_ids": [
                        fields.Command.create({
                            "source_field_id": mapping[c.source_field_id].id,
                            "operator": c.operator,
                            "value": c.value,
                        })
                        for c in rule.condition_ids
                    ],
                })
            if form.title_field_id in mapping:
                new.title_field_id = mapping[form.title_field_id]
        return new_forms

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------

    def _visible_values(self, raw_values):
        """Normalize answers and drop the ones whose question is hidden.

        Questions only depend on earlier ones, so one pass in order is enough.
        Returns ``(visible fields, {field id: value})``.
        """
        self.ensure_one()
        visible = self.env["angels.form.field"]
        values = {}
        section_shown = True
        for field in self.field_ids.sorted(lambda f: f._position()):
            shown = field._conditions_met(values)
            if field.field_type == "section":
                section_shown = shown
            else:
                shown = shown and section_shown
                raw = raw_values.get(field.id, raw_values.get(str(field.id)))
                values[field.id] = field._normalize(raw) if shown else False
            if shown:
                visible |= field
        return visible, values

    def _can_submit(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        return (
            self.active
            and self.published
            and user.has_group("angels_forms.group_form_user")
            and (not self.group_ids or bool(self.group_ids & user.all_group_ids))
            and (not self.company_id or self.company_id in user.company_ids)
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_designer(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "angels_forms_designer",
            "name": self.name,
            "context": {"active_id": self.id},
        }

    def action_fill(self):
        self.ensure_one()
        if not self._can_submit():
            raise AccessError(_("You cannot fill the form %(form)s.", form=self.name))
        return {
            "type": "ir.actions.client",
            "tag": "angels_forms_fill",
            "name": self.name,
            "context": {"form_id": self.id},
        }

    def action_view_submissions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("angels_forms.action_submission_all")
        action["domain"] = [("form_id", "=", self.id), ("state", "!=", "draft")]
        action["context"] = {}
        return action

    def action_publish(self):
        self.write({"published": True})

    def action_unpublish(self):
        self.write({"published": False})

    # ------------------------------------------------------------------
    # Designer
    # ------------------------------------------------------------------

    def get_design_data(self):
        self.ensure_one()
        self.check_access("write")
        return {
            "form": {
                "id": self.id,
                "name": self.name,
                "description": self.description or "",
                "icon": self.icon or "",
                "published": self.published,
                "title_field_id": self.title_field_id.id,
            },
            "fields": [field._to_client() for field in self.field_ids],
            "rules": [rule._to_client() for rule in self.rule_ids],
            "labels": {
                "types": dict(self._fields_selection("angels.form.field", "field_type")),
                "operators": dict(self._fields_selection("angels.form.condition", "operator")),
                "rule_types": dict(self._fields_selection("angels.form.rule", "rule_type")),
            },
            "operators_by_type": OPERATORS_BY_TYPE,
        }

    def _fields_selection(self, model, field_name):
        field = self.env[model]._fields[field_name]
        return field._description_selection(self.env)

    def save_design(self, data):
        """Save the whole designer state.

        Fields and rules that are new in the designer carry a string id
        (``"new_3"``); conditions refer to fields by that same id.
        """
        self.ensure_one()
        self.check_access("write")
        form_data = data.get("form", {})
        Field = self.env["angels.form.field"]
        Rule = self.env["angels.form.rule"]
        self.write({key: form_data[key] for key in ("name", "description", "icon") if key in form_data})

        fields_by_client_id = {}
        current_fields = self.field_ids
        for index, item in enumerate(data.get("fields", [])):
            vals = {key: item[key] for key in FIELD_KEYS if key in item}
            if "type" in item:
                vals["field_type"] = item["type"]
            if "match" in item:
                vals["condition_match"] = item["match"]
            vals["options"] = "\n".join(item.get("options") or [])
            vals["sequence"] = (index + 1) * 10
            field = current_fields.filtered(lambda f, cid=item.get("id"): f.id == cid)
            if field:
                field.write(vals)
            else:
                field = Field.create(dict(vals, form_id=self.id))
            fields_by_client_id[item.get("id")] = field
        kept = Field.union(*fields_by_client_id.values())
        removed = current_fields - kept
        answered = removed.filtered(
            lambda f: self.env["angels.form.answer"].sudo().search_count([("field_id", "=", f.id)], limit=1)
        )
        answered.write({"active": False})
        (removed - answered).unlink()

        def conditions(items):
            commands = []
            for item in items or []:
                source = fields_by_client_id.get(item.get("source_id"))
                if not source:
                    continue
                commands.append(fields.Command.create({
                    "source_field_id": source.id,
                    "operator": item.get("operator") or "=",
                    "value": item.get("value") or False,
                }))
            return commands

        for item in data.get("fields", []):
            field = fields_by_client_id[item.get("id")]
            field.condition_ids.unlink()
            field.condition_ids = conditions(item.get("conditions"))

        current_rules = self.rule_ids
        kept_rules = Rule
        for index, item in enumerate(data.get("rules", [])):
            vals = {key: item[key] for key in RULE_KEYS if key in item}
            if "match" in item:
                vals["condition_match"] = item["match"]
            user_field = fields_by_client_id.get(item.get("user_field_id"))
            vals.update({
                "sequence": (index + 1) * 10,
                "user_ids": [fields.Command.set(item.get("user_ids") or [])],
                "group_id": item.get("group_id") or False,
                "user_field_id": user_field.id if user_field else False,
                "condition_ids": conditions(item.get("conditions")),
            })
            rule = current_rules.filtered(lambda r, cid=item.get("id"): r.id == cid)
            if rule:
                rule.condition_ids.unlink()
                rule.write(vals)
            else:
                rule = Rule.create(dict(vals, form_id=self.id))
            kept_rules |= rule
        (current_rules - kept_rules).unlink()

        title = fields_by_client_id.get(form_data.get("title_field_id"))
        self.title_field_id = title or False
        return self.get_design_data()

    # ------------------------------------------------------------------
    # Filling
    # ------------------------------------------------------------------

    @api.model
    def get_fill_data(self, form_id, submission_id=False):
        """Everything the fill screen needs: questions and the current answers."""
        Submission = self.env[SUBMISSION_MODEL]
        values = {}
        submission_info = False
        if submission_id:
            submission = Submission.browse(submission_id)
            submission.check_access("read")
            if submission.state != "draft" or submission.user_id != self.env.user:
                raise UserError(_("Only the requester can change a draft request."))
            form = submission.form_id
            values = submission._answers_to_client()
            submission_info = {"id": submission.id, "name": submission.name}
        else:
            form = self.browse(form_id)
        if not form._can_submit():
            raise AccessError(_("You cannot fill the form %(form)s.", form=form.name))
        return {
            "form": {
                "id": form.id,
                "name": form.name,
                "description": form.description or "",
                "icon": form.icon or "",
            },
            "fields": [field._to_client() for field in form.field_ids],
            "values": values,
            "submission": submission_info,
        }
