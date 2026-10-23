import re
from datetime import datetime, time

from markupsafe import Markup
from psycopg2 import Error as DatabaseError

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.angels_flow.models.flow_node import DEFER

from .form_condition import TRUE_WORDS, is_set

SOURCES = [
    ("question", "Answer"),
    ("requester", "Requester"),
    ("value", "Fixed Value"),
    ("template", "Text with Answers"),
]
TEXT_TYPES = ("char", "text", "html")
# Kinds of question each kind of Odoo field accepts. Kept in sync with
# static/src/designer/record_editor.js.
AS_TEXT = ("char", "text", "number", "date", "datetime", "boolean", "selection", "multi", "user", "partner")
QUESTION_TYPES = {
    "char": AS_TEXT,
    "text": AS_TEXT,
    "html": AS_TEXT,
    "integer": ("number",),
    "float": ("number",),
    "monetary": ("number",),
    "boolean": ("boolean",),
    "date": ("date", "datetime"),
    "datetime": ("datetime", "date"),
    "selection": ("selection", "char"),
    "many2one": ("user", "partner"),
    "many2many": ("user", "partner"),
}
# A user question also fills a contact field (with the user's contact).
RELATION_QUESTIONS = {"res.users": ("user",), "res.partner": ("user", "partner")}
# Technical models a step may never create, whatever the rights of the designer.
BLOCKED_MODELS = ("res.company", "res.currency", "res.lang")
BLOCKED_PREFIXES = (
    "ir.", "base.", "bus.", "res.config", "res.users", "res.groups", "res.device", "auth",
    "mail.mail", "mail.message", "mail.followers", "mail.alias", "mail.notification",
    "angels.form", "iap.", "_",
)
MAGIC_FIELDS = ("id", "create_uid", "create_date", "write_uid", "write_date", "display_name")
FIELD_PREFIXES = ("message_", "activity_", "website_message", "rating_")
# {12}: answer to question 12; {reference} and {requester}: the request.
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def record_model_allowed(env, name):
    if not name or name not in env.registry or name in BLOCKED_MODELS or name.startswith(BLOCKED_PREFIXES):
        return False
    model = env[name]
    return not model._abstract and not model._transient and model._auto


def record_field_allowed(field):
    return (
        field.type in QUESTION_TYPES
        and field.store
        and not field.related
        and not (field.compute and field.readonly)
        and field.name not in MAGIC_FIELDS
        and not field.name.startswith(FIELD_PREFIXES)
    )


class AngelsFormMapping(models.Model):
    """One field of the record a Create Record step makes, and where its value comes from."""

    _name = "angels.form.mapping"
    _description = "Form Record Field"
    _order = "node_id, sequence, id"

    node_id = fields.Many2one("angels.form.node", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    field_name = fields.Char(string="Odoo Field", required=True)
    source = fields.Selection(SOURCES, required=True, default="question")
    question_id = fields.Many2one("angels.form.field", string="Question", ondelete="cascade")
    value = fields.Char(help="Fixed value, or text where {reference}, {requester} and the answers are replaced.")

    @api.model_create_multi
    def create(self, vals_list):
        mappings = super().create(vals_list)
        mappings.node_id._check_record_access()
        mappings._check_access_to_fields()
        return mappings

    def write(self, vals):
        result = super().write(vals)
        if "field_name" in vals or "node_id" in vals:
            self._check_access_to_fields()
        return result

    def _check_access_to_fields(self):
        """Who designs the step must be allowed to write the fields it fills."""
        if self.env.su:
            return
        for mapping in self:
            field = mapping._target()
            if field and field.groups and not self.env.user.has_groups(field.groups):
                raise AccessError(_("You are not allowed to fill the field %(field)s.", field=field.string))

    @api.constrains("node_id", "field_name", "source", "question_id", "value")
    def _check_mapping(self):
        for mapping in self:
            node = mapping.node_id
            if node.node_type != "record" or not record_model_allowed(self.env, node.record_model):
                raise ValidationError(_("Only a Create Record step fills the fields of a record."))
            field = mapping._target()
            if not field or not record_field_allowed(field):
                raise ValidationError(_("The step %(step)s cannot fill the field %(field)s.",
                                        step=node.name, field=mapping.field_name))
            if mapping.source not in mapping._sources(field):
                raise ValidationError(_("The field %(field)s cannot take this kind of value.", field=field.string))
            if mapping.source == "question":
                question = mapping.question_id
                if question.form_id != node.form_id or question.field_type not in mapping._question_types(field):
                    raise ValidationError(_("The field %(field)s needs a question of a matching type.",
                                            field=field.string))
            elif mapping.source == "value":
                mapping._parse(field, mapping.value)
            elif mapping.source == "template":
                ids = {int(token) for token in PLACEHOLDER.findall(mapping.value or "") if token.isdigit()}
                if ids - set(node.form_id.with_context(active_test=False).field_ids.ids):
                    raise ValidationError(_("The text of %(field)s uses a question of another form.",
                                            field=field.string))

    def _target(self):
        self.ensure_one()
        model = self.node_id.record_model
        return self.env[model]._fields.get(self.field_name) if model in self.env.registry else None

    @api.model
    def _question_types(self, field):
        if field.type in ("many2one", "many2many"):
            return RELATION_QUESTIONS.get(field.comodel_name, ())
        return QUESTION_TYPES[field.type]

    @api.model
    def _sources(self, field):
        sources = ["question", "value"]
        if field.type in TEXT_TYPES:
            sources += ["requester", "template"]
        elif field.comodel_name in RELATION_QUESTIONS:
            sources.append("requester")
        return sources

    # ------------------------------------------------------------------
    # Values
    # ------------------------------------------------------------------

    def _compute_value(self, submission, values):
        """Value to write in the field, or ``None`` to leave it to its default."""
        self.ensure_one()
        field = self._target()
        if self.source == "value":
            return self._parse(field, self.value)
        if self.source == "template":
            return self.node_id._render_text(self.value, submission)
        if self.source == "requester":
            return self._relational(field, submission.user_id) if field.relational else submission.user_id.name
        question = self.question_id
        value = values.get(question.id, False)
        if field.type == "boolean":
            return bool(value)
        if not is_set(value):
            return None
        if field.type in TEXT_TYPES:
            return submission._answer_text(question)
        if field.type == "integer":
            return round(value)
        if field.type in ("float", "monetary"):
            return value
        if field.type == "date":
            return value.date() if isinstance(value, datetime) else value
        if field.type == "datetime":
            return value if isinstance(value, datetime) else datetime.combine(value, time.min)
        if field.type == "selection":
            return self._selection_key(field, value)
        records = self.env["res.users" if question.field_type == "user" else "res.partner"].browse(value)
        return self._relational(field, records)

    def _relational(self, field, records):
        records = records.sudo().exists()
        if field.comodel_name == "res.partner" and records._name == "res.users":
            records = records.partner_id
        if field.type == "many2one":
            return records[:1].id or None
        return [fields.Command.set(records.ids)]

    def _parse(self, field, raw):
        """A fixed value typed in the designer, checked against the field."""
        raw = (raw or "").strip()
        if field.type == "boolean":
            return raw.lower() in TRUE_WORDS
        if not raw:
            return None
        try:
            if field.type in TEXT_TYPES:
                return raw
            if field.type == "integer":
                return int(raw)
            if field.type in ("float", "monetary"):
                return float(raw)
            if field.type == "date":
                return fields.Date.to_date(raw)
            if field.type == "datetime":
                return fields.Datetime.to_datetime(raw)
            if field.type == "selection":
                return self._selection_key(field, raw)
            ids = [int(part) for part in raw.split(",") if part.strip()]
        except ValueError:
            raise ValidationError(_("“%(value)s” is not a valid value for %(field)s.",
                                    value=raw, field=field.string)) from None
        return self._relational(field, self.env[field.comodel_name].browse(ids))

    def _selection_key(self, field, text):
        text = str(text).strip().lower()
        for key, label in field._description_selection(self.env):
            if text in (str(key).lower(), str(label).lower()):
                return key
        raise ValidationError(_("“%(value)s” is not one of the choices of %(field)s.",
                                value=text, field=field.string))


class AngelsFormLink(models.Model):
    """A record a request created in Odoo, through a Create Record step."""

    _name = "angels.form.link"
    _description = "Record Created by a Request"
    _order = "id"

    submission_id = fields.Many2one(
        "angels.form.submission", required=True, ondelete="cascade", index=True, readonly=True,
    )
    node_id = fields.Many2one("angels.form.node", string="Step", ondelete="set null", readonly=True)
    res_model = fields.Char(string="Model", required=True, readonly=True)
    res_id = fields.Many2oneReference(string="Record ID", model_field="res_model", required=True, readonly=True)
    name = fields.Char(string="Record", readonly=True)
    model_name = fields.Char(string="Type", compute="_compute_model_name")

    @api.depends("res_model")
    def _compute_model_name(self):
        for link in self:
            link.model_name = self.env["ir.model"]._get(link.res_model).name or link.res_model

    def action_open(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "views": [[False, "form"]],
        }


class AngelsFormNodeRecord(models.Model):
    _inherit = "angels.form.node"

    node_type = fields.Selection(
        selection_add=[("notify",), ("record", "Create Record")], ondelete={"record": "cascade"},
    )
    record_model = fields.Char(
        string="Record Type", help="Odoo model of the record to create, for example res.partner.",
    )
    attach_files = fields.Boolean(
        string="Attach the Files", default=True,
        help="Copy the files of the request onto the new record.",
    )
    mapping_ids = fields.One2many("angels.form.mapping", "node_id", string="Fields to Fill", copy=False)

    @api.model
    def _flow_ports(self):
        return {**super()._flow_ports(), "record": ("next",)}

    @api.model_create_multi
    def create(self, vals_list):
        nodes = super().create(vals_list)
        nodes._check_record_access()
        return nodes

    def write(self, vals):
        result = super().write(vals)
        if "record_model" in vals:
            self._check_record_access()
        return result

    def _check_record_access(self):
        """No step creates records its designer could not create by hand."""
        if self.env.su:
            return
        for node in self.filtered(lambda n: n.node_type == "record" and n.record_model):
            allowed = record_model_allowed(self.env, node.record_model)
            if allowed and not self.env[node.record_model].has_access("create"):
                raise AccessError(_("You cannot create %(model)s records, so no step of yours can.",
                                    model=self.env["ir.model"]._get(node.record_model).name))

    @api.constrains("node_type", "record_model")
    def _check_record_model(self):
        if self.env.context.get(DEFER):
            return
        for node in self.filtered(lambda n: n.node_type == "record"):
            if not record_model_allowed(self.env, node.record_model):
                raise ValidationError(_("The step %(step)s needs a kind of record to create.", step=node.name))

    def _render_text(self, text, submission):
        """Replace {reference}, {requester} and {question id} by their value."""
        self.ensure_one()
        questions = {str(f.id): f for f in self.form_id.with_context(active_test=False).field_ids}

        def replace(match):
            token = match.group(1)
            if token == "reference":
                return submission.name
            if token == "requester":
                return submission.user_id.name
            if token in questions:
                return submission._answer_text(questions[token])
            return match.group(0)

        return PLACEHOLDER.sub(replace, text or "") or None

    def _missing_fields(self, model, vals):
        required = [
            name for name, field in model._fields.items()
            if field.required and field.store and not field.compute and field.type != "boolean"
            and name not in MAGIC_FIELDS
            and vals.get(name) in (None, False, "")
        ]
        defaults = model.default_get(required)
        return [name for name in required if not defaults.get(name)]

    def _create_record(self, submission, values):
        """Create this step's record for ``submission``; a request creates it only once."""
        self.ensure_one()
        Link = self.env["angels.form.link"].sudo()
        if Link.search_count([("submission_id", "=", submission.id), ("node_id", "=", self.id)], limit=1):
            return Link.browse()
        model_label = self.env["ir.model"]._get(self.record_model).name
        if not record_model_allowed(self.env, self.record_model):
            raise UserError(_("The step %(step)s cannot create records any more.", step=self.name))
        Model = self.env[self.record_model].sudo().with_company(submission.company_id or self.env.company)
        vals = {}
        for mapping in self.mapping_ids:
            value = mapping._compute_value(submission, values)
            if value is not None:
                vals[mapping.field_name] = value
        missing = self._missing_fields(Model, vals)
        if missing:
            labels = ", ".join(Model._fields[name]._description_string(self.env) for name in missing)
            raise UserError(_("The step %(step)s could not create the %(model)s: %(fields)s is empty.",
                              step=self.name, model=model_label, fields=labels))
        try:
            with self.env.cr.savepoint():
                record = Model.create(vals)
        except (UserError, ValidationError, ValueError, TypeError, DatabaseError) as error:
            raise UserError(_("The step %(step)s could not create the %(model)s: %(error)s",
                              step=self.name, model=model_label, error=str(error))) from error
        if self.attach_files:
            files = self.form_id.field_ids.filtered(lambda f: f.field_type == "file")
            ids = [attachment for field in files for attachment in values.get(field.id) or []]
            for attachment in self.env["ir.attachment"].sudo().browse(ids).exists():
                attachment.copy({"res_model": record._name, "res_id": record.id})
        link = Link.create({
            "submission_id": submission.id,
            "node_id": self.id,
            "res_model": record._name,
            "res_id": record.id,
            "name": record.display_name,
        })
        submission.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(step)s: %(model)s %(record)s created.",
                                         step=self.name, model=model_label, record=record._get_html_link()),
            subtype_xmlid="mail.mt_note",
        )
        if hasattr(record, "message_post"):
            record.message_post(
                body=Markup("<p>%s</p>") % _("Created from the request %(request)s.",
                                             request=submission._get_html_link()),
                subtype_xmlid="mail.mt_note",
            )
        return link

    def _to_client(self):
        data = super()._to_client()
        data.update({
            "record_model": self.record_model or False,
            "record_model_name": self.record_model and self.env["ir.model"]._get(self.record_model).name or "",
            "attach_files": self.attach_files,
            "mappings": [
                {
                    "field": mapping.field_name,
                    "source": mapping.source,
                    "question_id": mapping.question_id.id,
                    "value": mapping.value or "",
                }
                for mapping in self.mapping_ids
            ],
        })
        return data
