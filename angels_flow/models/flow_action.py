from datetime import timedelta

from lxml import etree
from markupsafe import Markup
from psycopg2 import Error as DatabaseError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .flow_condition import TRUE_WORDS, field_kind, record_value

SOURCES = [
    ("value", "Fixed Value"),
    ("today", "Today + Days"),
    ("starter", "Who Started the Run"),
    ("empty", "Empty"),
]
# Types of field an Update Record step can set.
UPDATE_TYPES = ("char", "text", "html", "integer", "float", "monetary", "boolean", "selection",
                "date", "datetime", "many2one")
MAGIC_FIELDS = ("id", "create_uid", "create_date", "write_uid", "write_date", "display_name")


def update_field_allowed(field):
    """Whether an Update Record step may set this ``ir.model.fields`` record."""
    return (
        field.ttype in UPDATE_TYPES
        and field.store
        and not field.related
        and not field.readonly
        and field.name not in MAGIC_FIELDS
        and not field.name.startswith(("message_", "activity_", "website_message"))
    )


class AngelsFlowUpdate(models.Model):
    """One field an Update Record step sets, and the value it gets."""

    _name = "angels.flow.update"
    _description = "Flow Update"
    _order = "sequence, id"

    node_id = fields.Many2one("angels.flow.node", string="Flow Step", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer()
    field_id = fields.Many2one("ir.model.fields", string="Field", required=True, ondelete="cascade")
    source = fields.Selection(SOURCES, required=True, default="value")
    value = fields.Char()
    days = fields.Integer(help="For Today + Days: how many days after today (negative: before).")

    @api.constrains("node_id", "field_id", "source")
    def _check_update(self):
        for update in self:
            field = update.field_id
            if field.model != update.node_id.flow_id.model_name or not update_field_allowed(field):
                raise ValidationError(_("The step %(step)s cannot set the field %(field)s.",
                                        step=update.node_id.name, field=field.field_description))
            if update.source == "today" and field.ttype not in ("date", "datetime"):
                raise ValidationError(_("Only a date can be set to today."))
            if update.source == "starter" and not (field.ttype == "many2one" and field.relation == "res.users"):
                raise ValidationError(_("Only a user field can be set to who started the run."))

    def _compute_value(self, run):
        """The value to write, as ``write`` expects it."""
        self.ensure_one()
        field = self.field_id
        if self.source == "empty":
            return False
        if self.source == "starter":
            return run.user_id.id
        if self.source == "today":
            if field.ttype == "date":
                return fields.Date.context_today(run) + timedelta(days=self.days)
            return fields.Datetime.now() + timedelta(days=self.days)
        raw = (self.value or "").strip()
        try:
            if field.ttype == "boolean":
                return raw.lower() in TRUE_WORDS
            if not raw:
                return False
            if field.ttype == "integer":
                return int(float(raw))
            if field.ttype in ("float", "monetary"):
                return float(raw)
            if field.ttype == "many2one":
                return int(raw)
            if field.ttype == "date":
                return fields.Date.to_date(raw)
            if field.ttype == "datetime":
                return fields.Datetime.to_datetime(raw)
        except (TypeError, ValueError):
            raise UserError(_("The value %(value)s does not fit the field %(field)s.",
                              value=raw, field=field.field_description)) from None
        return raw

    def _to_client(self):
        return {
            "field_id": self.field_id.id,
            "source": self.source,
            "value": self.value or "",
            "days": self.days,
        }


class AngelsFlowNodeAction(models.Model):
    """The Update Record and Action steps of flows on records."""

    _inherit = "angels.flow.node"

    node_type = fields.Selection(
        selection_add=[("wait",), ("update", "Update Record"), ("action", "Run an Action")],
        ondelete={"update": "cascade", "action": "cascade"},
    )
    update_ids = fields.One2many("angels.flow.update", "node_id", string="Fields to Set", copy=True)
    action_ref = fields.Char(
        string="Action",
        help="What the step does: button:<method> (a button of the record), server:<id> "
             "(a server action) or preset:<key> (an action added by another module).",
    )

    @api.model
    def _flow_ports(self):
        return {**super()._flow_ports(), "update": ("next",), "action": ("next",)}

    @api.constrains("node_type", "action_ref")
    def _check_action(self):
        if self.env.context.get("angels_flow_defer"):
            return
        for node in self.filtered(lambda n: n.node_type == "action"):
            keys = {choice["key"] for choice in node.flow_id._flow_action_choices()}
            if node.action_ref not in keys:
                raise ValidationError(_("The step %(step)s needs an action of this model.", step=node.name))

    def _flow_apply_updates(self, run):
        self.ensure_one()
        record = run._record()
        if not record:
            raise UserError(_("The record of %(run)s no longer exists.", run=run.display_name))
        vals = {update.field_id.name: update._compute_value(run) for update in self.update_ids}
        if not vals:
            return
        self._flow_safely(lambda: record.write(vals))
        run.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(step)s: %(fields)s updated.", step=self.name,
                                         fields=", ".join(self.update_ids.field_id.mapped("field_description"))),
            subtype_xmlid="mail.mt_note",
        )

    def _flow_run_action(self, run):
        self.ensure_one()
        record = run._record()
        if not record:
            raise UserError(_("The record of %(run)s no longer exists.", run=run.display_name))
        kind, __, key = (self.action_ref or "").partition(":")
        choices = {choice["key"]: choice for choice in self.flow_id._flow_action_choices()}
        if self.action_ref not in choices:
            raise UserError(_("The step %(step)s has no action to run.", step=self.name))
        if kind == "button":
            self._flow_safely(lambda: self._flow_press_button(record, key))
        elif kind == "server":
            action = self.env["ir.actions.server"].sudo().browse(int(key))
            context = {"active_model": record._name, "active_id": record.id, "active_ids": record.ids}
            self._flow_safely(lambda: action.with_context(**context).run())
        else:
            self._flow_safely(lambda: self._flow_run_preset(key, record))
        run.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(step)s: %(action)s done.", step=self.name,
                                         action=choices[self.action_ref]["label"]),
            subtype_xmlid="mail.mt_note",
        )

    def _flow_press_button(self, record, method):
        result = getattr(record, method)()
        if isinstance(result, dict) and result.get("type") == "ir.actions.act_window":
            # It would ask someone to fill a window: nobody is there to do it.
            raise UserError(_("this button opens a window to fill, it cannot run by itself"))
        return result

    def _flow_run_preset(self, key, record):
        """Run an action added by another module (see ``angels.flow._flow_action_choices``)."""
        raise UserError(_("The step %(step)s cannot run.", step=self.name))

    def _flow_safely(self, function):
        """Run ``function``; its errors stop the flow with the name of the step."""
        try:
            with self.env.cr.savepoint():
                return function()
        except (UserError, ValidationError) as error:
            raise UserError(_("The step %(step)s could not finish: %(error)s",
                              step=self.name, error=error.args[0] if error.args else error)) from error
        except DatabaseError as error:
            raise UserError(_("The step %(step)s could not finish: the database refused the change.",
                              step=self.name)) from error

    def _to_client(self):
        data = super()._to_client()
        data.update({
            "updates": [update._to_client() for update in self.update_ids],
            "action_ref": self.action_ref or False,
        })
        return data


class AngelsFlowActions(models.Model):
    _inherit = "angels.flow"

    def _update_fields(self):
        self.ensure_one()
        return self.env["ir.model.fields"].sudo().search([("model_id", "=", self.model_id.id)]).filtered(
            update_field_allowed
        ).sorted(lambda f: f.field_description.lower())

    def _flow_action_choices(self):
        """What an Action step can do on this flow's records: [{key, label, group}].

        The buttons of the record's form (type "object"), its server actions,
        and the presets other modules add (``preset:<key>``).
        """
        self.ensure_one()
        Model = self.env[self.model_name].sudo()
        choices = []
        seen = set()
        arch = etree.fromstring(Model.get_view(view_type="form")["arch"])
        for button in arch.xpath("//header//button[@type='object']"):
            name = button.get("name") or ""
            if name.startswith("_") or name in seen or not hasattr(Model, name):
                continue
            seen.add(name)
            choices.append({"key": f"button:{name}", "label": button.get("string") or name,
                            "group": _("Buttons")})
        actions = self.env["ir.actions.server"].sudo().search([
            ("model_id", "=", self.model_id.id), ("state", "!=", "angels_flow"),
            ("usage", "=", "ir_actions_server"),
        ])
        choices += [{"key": f"server:{action.id}", "label": action.name, "group": _("Server Actions")}
                    for action in actions]
        return choices


class AngelsFlowSimulation(models.Model):
    _inherit = "angels.flow"

    def get_step_stats(self):
        """How long the people of each step take, for the designer."""
        self.ensure_one()
        self.check_access("write")
        return self.env["angels.flow.run.step"]._flow_stats(self.node_ids)

    def simulate(self, res_id):
        """The way a record would go through the flow, without changing anything.

        Approvals are taken as approved and waits as over. Returns the steps in
        order, each with what would happen there.
        """
        self.ensure_one()
        self.check_access("write")
        record = self.env[self.model_name].browse(int(res_id)).exists()
        if not record:
            raise UserError(_("This record does not exist."))
        record.check_access("read")
        record = record.sudo()
        matches = bool(record.filtered_domain(self._records_domain()))
        nodes = self.node_ids
        used = nodes.condition_ids.field_id | nodes.user_field_id
        values = {field.name: record_value(record, field) for field in used if field_kind(field)}
        choices = {choice["key"]: choice["label"] for choice in self._flow_action_choices()}
        path, seen = [], set()
        node = self._start_node()
        end = None
        while node:
            if node.id in seen:
                path.append({"node": node.id, "text": _("The flow would go round in a circle here."), "error": True})
                break
            seen.add(node.id)
            kind = node.node_type
            entry = {"node": node.id, "text": ""}
            path.append(entry)
            if kind == "start":
                entry["text"] = _("Starts for %(record)s.", record=record.display_name)
                node = node.next_id
            elif kind == "condition":
                met = node._flow_condition_met(values)
                entry["text"] = _("Yes: the conditions are met.") if met else _("No: the conditions are not met.")
                node = node.yes_id if met else node.no_id
            elif kind in ("approve", "task", "notify"):
                people = node._get_recipients(values)
                names = ", ".join(people.mapped("name"))
                if not people:
                    entry.update(text=_("Nobody can do this step: the run would stop here."), error=kind != "notify")
                    if kind != "notify":
                        break
                elif kind == "approve":
                    entry["text"] = _("Approval by %(people)s; if they approve, it goes on.", people=names)
                elif kind == "task":
                    entry["text"] = _("%(people)s would complete it.", people=names)
                else:
                    entry["text"] = _("%(people)s would be informed.", people=names)
                node = node.next_id
            elif kind == "wait":
                amount = node.wait_amount
                entry["text"] = (_("Waits %(amount)s hours.", amount=amount) if node.wait_unit == "hours"
                                 else _("Waits %(amount)s days.", amount=amount))
                node = node.next_id
            elif kind == "update":
                entry["text"] = _("Would set: %(fields)s.", fields=", ".join(node.update_ids.field_id.mapped("field_description")))
                node = node.next_id
            elif kind == "action":
                entry["text"] = _("Would run: %(action)s.", action=choices.get(node.action_ref, "?"))
                node = node.next_id
            elif kind == "end":
                end = node.end_state or "approved"
                entry["text"] = _("Ends: approved.") if end == "approved" else _("Ends: rejected.")
                node = False
            else:
                node = node.next_id
        if end is None and not (path and path[-1].get("error")):
            end = "approved"
            path.append({"node": False, "text": _("No more steps: the run would be approved.")})
        return {"matches": matches, "path": path, "record": record.display_name}
