from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.angels_flow.models.flow_node import DEFER, PORT_FIELDS

from .form_condition import OPERATORS_BY_TYPE
from .form_record import PLACEHOLDER, record_field_allowed, record_model_allowed

SUBMISSION_MODEL = "angels.form.submission"
FIELD_KEYS = ("name", "required", "help", "placeholder", "prefix", "suffix", "width")
SETTING_KEYS = ("name", "description", "icon", "color", "allow_self_approval")
NODE_KEYS = ("name", "end_state", "assign_type", "approval_rule", "deadline_amount", "deadline_unit", "on_deadline")
START_POSITION = (40, 160)


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
    node_ids = fields.One2many("angels.form.node", "form_id", string="Flow")
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
    node_count = fields.Integer(compute="_compute_counts")

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

    @api.depends("field_ids", "node_ids")
    def _compute_counts(self):
        for form in self:
            form.field_count = len(form.field_ids.filtered(lambda f: f.field_type != "section"))
            form.node_count = len(form.node_ids.filtered(lambda n: n.node_type != "start"))

    @api.constrains("title_field_id")
    def _check_title_field(self):
        for form in self:
            if form.title_field_id and form.title_field_id.form_id != form:
                raise ValidationError(_("The title must come from a question of the same form."))

    @api.model_create_multi
    def create(self, vals_list):
        forms = super().create(vals_list)
        forms._ensure_start()
        return forms

    def _ensure_start(self):
        if self.env.context.get("angels_forms_no_start"):
            return
        for form in self.filtered(lambda f: not f.node_ids.filtered(lambda n: n.node_type == "start")):
            self.env["angels.form.node"].create({
                "form_id": form.id,
                "name": _("Request Sent"),
                "node_type": "start",
                "pos_x": START_POSITION[0],
                "pos_y": START_POSITION[1],
            })

    def _start_node(self):
        self.ensure_one()
        return self.node_ids.filtered(lambda n: n.node_type == "start")[:1]

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        for form, vals in zip(self, vals_list):
            vals.setdefault("name", _("%s (copy)", form.name))
            vals["published"] = False
            vals.pop("title_field_id", None)
        return vals_list

    def copy(self, default=None):
        # Fields and steps point at each other: rebuild the links on the copy.
        new_forms = super().copy(default=default)
        for form, new in zip(self, new_forms):
            new.node_ids.unlink()
            field_map = dict(zip(form.field_ids, new.field_ids))
            node_map = {
                node: node.copy({
                    "form_id": new.id,
                    "user_field_id": field_map.get(node.user_field_id, node.user_field_id.browse()).id,
                    **{name: False for name in PORT_FIELDS.values()},
                })
                for node in form.node_ids
            }

            def conditions(items):
                return [
                    fields.Command.create({
                        "source_field_id": field_map[c.source_field_id].id,
                        "operator": c.operator,
                        "value": c.value,
                    })
                    for c in items
                    if c.source_field_id in field_map
                ]

            ids = {str(field.id): new_field.id for field, new_field in field_map.items()}
            for node, new_node in node_map.items():
                new_node.write({
                    **{name: node_map.get(node[name], node[name].browse()).id for name in PORT_FIELDS.values()},
                    "condition_ids": conditions(node.condition_ids),
                    "mapping_ids": [
                        fields.Command.create({
                            "field_name": m.field_name,
                            "source": m.source,
                            "question_id": field_map.get(m.question_id, m.question_id.browse()).id,
                            "value": self._replace_question_ids(m.value, ids),
                        })
                        for m in node.mapping_ids
                        if m.source != "question" or m.question_id in field_map
                    ],
                })
            for field, new_field in field_map.items():
                new_field.write({
                    "node_id": node_map.get(field.node_id, field.node_id.browse()).id,
                    "condition_ids": conditions(field.condition_ids),
                })
            if form.title_field_id in field_map:
                new.title_field_id = field_map[form.title_field_id]
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

    def _requester_fields(self):
        self.ensure_one()
        return self.field_ids.filtered(lambda f: not f.node_id)

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

    def action_new_form(self):
        """New button of the list: create a form and open it in the designer.

        Header buttons pass the selected rows (usually none); they are ignored.
        """
        form = self.browse().create({"name": _("New Form")})
        action = form.action_open_designer()
        action["context"]["angels_forms_new"] = True
        return action

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
        self._ensure_start()
        return {
            "form": {
                "id": self.id,
                "name": self.name,
                "description": self.description or "",
                "icon": self.icon or "",
                "published": self.published,
                "title_field_id": self.title_field_id.id,
                "color": self.color,
                "group_ids": self.group_ids.ids,
                "company_id": self.company_id.id,
                "allow_self_approval": self.allow_self_approval,
            },
            "multi_company": self.env.user.has_group("base.group_multi_company"),
            "fields": [field._to_client() for field in self.field_ids],
            "nodes": [node._to_client() for node in self.node_ids],
            "labels": {
                "types": dict(self._fields_selection("angels.form.field", "field_type")),
                "widths": dict(self._fields_selection("angels.form.field", "width")),
                "operators": dict(self._fields_selection("angels.form.condition", "operator")),
                "node_types": dict(self._fields_selection("angels.form.node", "node_type")),
                "sources": dict(self._fields_selection("angels.form.mapping", "source")),
            },
            "operators_by_type": OPERATORS_BY_TYPE,
            "ports": self.env["angels.form.node"]._flow_ports(),
        }

    @api.model
    def _replace_question_ids(self, text, ids):
        """In the text of a mapping, point {question id} placeholders at other ids."""
        if not text:
            return text
        return PLACEHOLDER.sub(lambda m: "{%s}" % ids.get(m.group(1), m.group(1)), text)

    @api.model
    def get_record_models(self):
        """Kinds of record the current designer may make a step create."""
        self.env["angels.form"].check_access("write")
        models_ = self.env["ir.model"].sudo().search([("transient", "=", False)])
        return sorted(
            (
                {"model": model.model, "name": model.name}
                for model in models_
                if record_model_allowed(self.env, model.model) and self.env[model.model].has_access("create")
            ),
            key=lambda m: m["name"].lower(),
        )

    @api.model
    def get_record_fields(self, model):
        """Fields of ``model`` a Create Record step can fill, required ones first."""
        self.env["angels.form"].check_access("write")
        if not record_model_allowed(self.env, model):
            raise UserError(_("A step cannot create %(model)s records.", model=model))
        Model = self.env[model]
        allowed = {
            name: field for name, field in Model._fields.items()
            if record_field_allowed(field) and (not field.groups or self.env.user.has_groups(field.groups))
        }
        missing = set(self.env["angels.form.node"]._missing_fields(Model, {}))
        result = [
            {
                "name": name,
                "label": field._description_string(self.env),
                "type": field.type,
                "relation": field.comodel_name or False,
                "required": name in missing,
                "selection": field._description_selection(self.env) if field.type == "selection" else False,
            }
            for name, field in allowed.items()
        ]
        return sorted(result, key=lambda f: (not f["required"], f["label"].lower()))

    def _fields_selection(self, model, field_name):
        field = self.env[model]._fields[field_name]
        return field._description_selection(self.env)

    def save_design(self, data):
        """Save the whole designer state.

        Questions and steps that are new in the designer carry a string id
        (``"new_3"``); conditions, links and "filled by" refer to them by that id.
        """
        self.ensure_one()
        self.check_access("write")
        form_data = data.get("form", {})
        Field = self.env["angels.form.field"]
        Node = self.env["angels.form.node"]
        vals = {key: form_data[key] for key in SETTING_KEYS if key in form_data}
        if "group_ids" in form_data:
            vals["group_ids"] = [fields.Command.set(form_data["group_ids"] or [])]
        if "company_id" in form_data:
            vals["company_id"] = form_data["company_id"] or False
        self.write(vals)

        # 1. Steps first: questions refer to the step that fills them.
        nodes_by_client_id = {}
        current_nodes = self.node_ids
        for item in data.get("nodes", []):
            vals = {key: item[key] for key in NODE_KEYS if key in item}
            vals.update({
                "node_type": item.get("type") or "approve",
                "pos_x": int(item.get("x") or 0),
                "pos_y": int(item.get("y") or 0),
                "color": int(item.get("color") or 0),
                "condition_match": item.get("match") or "all",
            })
            # Recipients are written and checked in step 4, once the user questions exist.
            node = current_nodes.filtered(lambda n, cid=item.get("id"): n.id == cid)
            if node:
                node.with_context(**{DEFER: True}).write(vals)
            else:
                node = Node.with_context(**{DEFER: True}).create(dict(vals, form_id=self.id))
            nodes_by_client_id[item.get("id")] = node.with_env(self.env)
        removed_nodes = current_nodes - Node.union(*nodes_by_client_id.values())

        # 2. Questions.
        fields_by_client_id = {}
        current_fields = self.field_ids
        for index, item in enumerate(data.get("fields", [])):
            vals = {key: item[key] for key in FIELD_KEYS if key in item}
            vals.update({
                "field_type": item.get("type") or "char",
                "condition_match": item.get("match") or "all",
                "options": "\n".join(item.get("options") or []),
                "sequence": (index + 1) * 10,
                "row": max(0, int(item.get("row") or 0)),
                "col": min(11, max(0, int(item.get("col") or 0))),
                "node_id": nodes_by_client_id.get(item.get("node_id"), Node).id,
            })
            field = current_fields.filtered(lambda f, cid=item.get("id"): f.id == cid)
            if field:
                field.write(vals)
            else:
                field = Field.create(dict(vals, form_id=self.id))
            fields_by_client_id[item.get("id")] = field
        removed = current_fields - Field.union(*fields_by_client_id.values())
        answered = removed.filtered(
            lambda f: self.env["angels.form.answer"].sudo().search_count([("field_id", "=", f.id)], limit=1)
        )
        answered.write({"active": False, "node_id": False})
        (removed - answered).unlink()

        def conditions(items):
            commands = []
            for item in items or []:
                source = fields_by_client_id.get(item.get("source_id"))
                if source:
                    commands.append(fields.Command.create({
                        "source_field_id": source.id,
                        "operator": item.get("operator") or "=",
                        "value": item.get("value") or False,
                    }))
            return commands

        # 3. "Show only if" of each question.
        for item in data.get("fields", []):
            field = fields_by_client_id[item.get("id")]
            field.condition_ids.unlink()
            field.condition_ids = conditions(item.get("conditions"))

        # 4. Links between steps, conditions and recipients.
        removed_nodes.unlink()
        ports = Node._flow_ports()
        for item in data.get("nodes", []):
            node = nodes_by_client_id[item.get("id")]
            links = item.get("links") or {}
            vals = {name: False for name in PORT_FIELDS.values()}
            for port in ports[node.node_type]:
                target = nodes_by_client_id.get(links.get(port))
                vals[PORT_FIELDS[port]] = target.id if target else False
            user_field = fields_by_client_id.get(item.get("user_field_id"))
            vals.update(self._record_vals(node, item, fields_by_client_id))
            node.condition_ids.unlink()
            vals.update({
                "assign_type": item.get("assign_type") or "users",
                "user_ids": [fields.Command.set(item.get("user_ids") or [])],
                "group_id": item.get("group_id") or False,
                "escalate_user_id": item.get("escalate_user_id") or False,
                "user_field_id": user_field.id if user_field else False,
                "condition_ids": conditions(item.get("conditions")),
            })
            node.write(vals)
        self._ensure_start()
        if len(self.node_ids.filtered(lambda n: n.node_type == "start")) != 1:
            raise ValidationError(_("A flow has only one Start."))

        title = fields_by_client_id.get(form_data.get("title_field_id"))
        self.title_field_id = title or False
        return self.get_design_data()

    def get_step_stats(self):
        """How long the people of each step take, for the designer."""
        self.ensure_one()
        self.check_access("write")
        return self.env["angels.form.step"]._flow_stats(self.node_ids)

    def _record_vals(self, node, item, fields_by_client_id):
        """What a Create Record step creates. Mappings are rewritten only when they change."""
        ids = {str(cid): field.id for cid, field in fields_by_client_id.items()}
        record = node.node_type == "record"
        model = record and item.get("record_model") or False
        vals = {"attach_files": bool(item.get("attach_files", True))}
        if model != (node.record_model or False):
            vals["record_model"] = model
        mappings = []
        for mapping in (item.get("mappings") or []) if record else []:
            source = mapping.get("source") or "question"
            question = fields_by_client_id.get(mapping.get("question_id")) if source == "question" else False
            mappings.append((
                mapping.get("field"),
                source,
                question.id if question else False,
                self._replace_question_ids(mapping.get("value"), ids) or False if source != "question" else False,
            ))
        current = [(m.field_name, m.source, m.question_id.id, m.value or False) for m in node.mapping_ids]
        if mappings != current or "record_model" in vals:
            node.mapping_ids.unlink()
            vals["mapping_ids"] = [
                fields.Command.create({
                    "sequence": index,
                    "field_name": field_name,
                    "source": source,
                    "question_id": question_id,
                    "value": value,
                })
                for index, (field_name, source, question_id, value) in enumerate(mappings)
            ]
        return vals

    # ------------------------------------------------------------------
    # Filling
    # ------------------------------------------------------------------

    @api.model
    def get_fill_data(self, form_id, submission_id=False):
        """Everything the fill screen needs: questions and the current answers.

        The requester gets their own questions. A reviewer whose turn it is gets
        the questions of their step to fill, and the earlier answers read-only.
        """
        Submission = self.env[SUBMISSION_MODEL]
        values = {}
        submission_info = False
        if submission_id:
            submission = Submission.browse(submission_id)
            submission.check_access("read")
            form = submission.form_id
            if submission.can_edit and not form._can_submit():
                raise AccessError(_("You cannot fill the form %(form)s.", form=form.name))
            if not submission.can_edit and not submission.is_my_turn:
                raise UserError(_("This request is not waiting for you."))
            editable = submission._editable_fields()
            shown = form._requester_fields() if submission.can_edit else submission._reached_fields()
            values = submission._answers_to_client()
            step = submission.sudo().current_step_id if not submission.can_edit else False
            submission_info = {
                "id": submission.id,
                "name": submission.display_name,
                "state": submission.state,
                "step": step and {
                    "name": step.name,
                    "type": step.step_type,
                    "color": step.node_id.color,
                } or False,
            }
        else:
            form = self.browse(form_id)
            if not form._can_submit():
                raise AccessError(_("You cannot fill the form %(form)s.", form=form.name))
            shown = editable = form._requester_fields()
        fields_data = []
        for field in form.field_ids:
            if field in shown:
                fields_data.append(dict(
                    field._to_client(),
                    editable=field in editable,
                    color=field.node_id.color,
                    stage=field.node_id.name or False,
                ))
        return {
            "form": {
                "id": form.id,
                "name": form.name,
                "description": form.description or "",
                "icon": form.icon or "",
            },
            "fields": fields_data,
            "values": values,
            "submission": submission_info,
        }
