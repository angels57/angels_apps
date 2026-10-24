import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import datetime as safe_eval_datetime
from odoo.tools.safe_eval import safe_eval

from .flow_condition import OPERATORS_BY_TYPE, field_kind
from .flow_node import DEFER, PORT_FIELDS

_logger = logging.getLogger(__name__)

TRIGGERS = [
    ("manual", "Manually"),
    ("on_create", "When a record is created"),
    ("on_create_or_write", "When a record is created or updated"),
    ("scheduled", "On a schedule"),
    ("on_time", "Around a date of the record"),
]
# Triggers run by an automation rule (base_automation).
AUTOMATION_TRIGGERS = ("on_create", "on_create_or_write", "on_time")
INTERVALS = [("hours", "Hours"), ("days", "Days"), ("weeks", "Weeks"), ("months", "Months")]
# No flow on the models of flows, nor on technical models.
BLOCKED_PREFIXES = ("angels.flow", "ir.", "base.automation", "mail.", "bus.", "res.groups", "res.users.")
NODE_KEYS = ("name", "end_state", "assign_type", "approval_rule", "wait_amount", "wait_unit", "action_ref",
             "deadline_amount", "deadline_unit", "on_deadline")


class AngelsFlow(models.Model):
    """A flow on the records of one model, started by hand, automatically or on a schedule."""

    _name = "angels.flow"
    _description = "Flow"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    is_example = fields.Boolean(
        string="Example", readonly=True, copy=False,
        help="An example shipped with the module: use it as it is, or as a start for your own flow.",
    )
    model_id = fields.Many2one(
        "ir.model", string="Applies To", required=True, ondelete="cascade",
        domain=[("transient", "=", False), ("abstract", "=", False)],
    )
    model_name = fields.Char(related="model_id.model", store=True, string="Model Name")
    trigger = fields.Selection(TRIGGERS, string="Starts", required=True, default="manual")
    filter_domain = fields.Char(
        string="Only Records", default="[]",
        help="The flow starts only on the records that match.",
    )
    trigger_field_ids = fields.Many2many(
        "ir.model.fields", string="When These Change",
        domain="[('model_id', '=', model_id), ('store', '=', True)]",
        help="Updates of other fields do not start the flow. Empty: any update.",
    )
    interval_number = fields.Integer(string="Every", default=1)
    interval_type = fields.Selection(INTERVALS, string="Unit", default="days")
    next_run = fields.Datetime(string="Next Run", default=fields.Datetime.now)
    date_field_id = fields.Many2one(
        "ir.model.fields", string="Date Field", ondelete="cascade",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]",
    )
    date_range = fields.Integer(string="Delay", default=1)
    date_range_type = fields.Selection([("hour", "Hours"), ("day", "Days")], string="Delay Unit", default="day")
    date_range_mode = fields.Selection([("before", "Before"), ("after", "After")], string="Delay Mode", default="before")
    once_per_record = fields.Boolean(
        string="Once per Record", default=True,
        help="A record goes through this flow only once. Otherwise it can start again once the last run is over.",
    )
    allow_self_approval = fields.Boolean(
        string="Self-Approval",
        help="Who started a run may also approve its steps. Off: someone else must approve them.",
    )
    node_ids = fields.One2many("angels.flow.node", "flow_id", string="Steps")
    run_ids = fields.One2many("angels.flow.run", "flow_id", string="Runs")
    run_count = fields.Integer(compute="_compute_run_count")
    running_count = fields.Integer(compute="_compute_run_count")
    action_id = fields.Many2one("ir.actions.server", string="Start Action", readonly=True, copy=False)
    automation_id = fields.Many2one("base.automation", string="Automation Rule", readonly=True, copy=False)

    @api.depends("run_ids.state")
    def _compute_run_count(self):
        for flow in self:
            flow.run_count = len(flow.run_ids)
            flow.running_count = len(flow.run_ids.filtered(lambda r: r.state == "pending"))

    @api.constrains("model_id")
    def _check_model(self):
        for flow in self:
            model = flow.model_name
            if model.startswith(BLOCKED_PREFIXES) or model not in self.env or not self.env[model]._auto:
                raise ValidationError(_("No flow can run on %(model)s.", model=flow.model_id.name))

    @api.constrains("trigger", "interval_number", "date_field_id")
    def _check_trigger(self):
        for flow in self:
            if flow.trigger == "scheduled" and flow.interval_number < 1:
                raise ValidationError(_("A scheduled flow runs at least every 1 %(unit)s.", unit=flow.interval_type))
            if flow.trigger == "on_time" and not flow.date_field_id:
                raise ValidationError(_("The flow %(flow)s needs a date field.", flow=flow.name))

    @api.model_create_multi
    def create(self, vals_list):
        flows = super().create(vals_list)
        # Example flows come with their own Start.
        for flow in flows.filtered(lambda f: not self.env.context.get("angels_flow_no_start")):
            flow.node_ids.create([
                {"flow_id": flow.id, "name": self.env._("Start"), "node_type": "start", "pos_x": 40, "pos_y": 160},
            ])
        flows._sync_automation()
        return flows

    def write(self, vals):
        result = super().write(vals)
        if {"active", "name", "model_id", "trigger", "filter_domain", "trigger_field_ids",
                "date_field_id", "date_range", "date_range_type", "date_range_mode"} & set(vals):
            self._sync_automation()
        return result

    def unlink(self):
        actions = self.action_id
        automations = self.automation_id
        result = super().unlink()
        automations.sudo().unlink()
        actions.sudo().unlink()
        return result

    def copy_data(self, default=None):
        vals_list = super().copy_data(default)
        return [dict(vals, name=self.env._("%s (copy)", flow.name)) for flow, vals in zip(self, vals_list)]

    def copy(self, default=None):
        new_flows = super().copy(default)
        for flow, new in zip(self, new_flows):
            new.node_ids.unlink()
            node_map = {node: node.copy({"flow_id": new.id, **{name: False for name in PORT_FIELDS.values()}})
                        for node in flow.node_ids}
            for node, new_node in node_map.items():
                new_node.write({
                    **{name: node_map.get(node[name], node[name].browse()).id for name in PORT_FIELDS.values()},
                    "condition_ids": [fields.Command.create({
                        "field_id": c.field_id.id, "operator": c.operator, "value": c.value,
                    }) for c in node.condition_ids],
                })
        return new_flows

    # ------------------------------------------------------------------
    # Starting the flow
    # ------------------------------------------------------------------

    def _sync_automation(self):
        """The server action that starts the flow, in the Action menu of its model, and the
        automation rule that starts it on create, update or around a date."""
        for flow in self.sudo():
            action_vals = {
                "name": self.env._("Start the flow %s", flow.name),
                "model_id": flow.model_id.id,
                "state": "angels_flow",
                "angels_flow_id": flow.id,
                "binding_model_id": flow.model_id.id if flow.active else False,
                "binding_type": "action",
            }
            if flow.action_id:
                flow.action_id.write(action_vals)
            else:
                flow.action_id = self.env["ir.actions.server"].create(action_vals)
            if not flow.active or flow.trigger not in AUTOMATION_TRIGGERS:
                flow.automation_id.unlink()
                continue
            automation_vals = {
                "name": self.env._("Flow: %s", flow.name),
                "model_id": flow.model_id.id,
                "trigger": flow.trigger,
                "filter_domain": flow.filter_domain or "[]",
                "trigger_field_ids": [fields.Command.set(flow.trigger_field_ids.ids if flow.trigger == "on_create_or_write" else [])],
                "trg_date_id": flow.date_field_id.id if flow.trigger == "on_time" else False,
                "trg_date_range": flow.date_range,
                "trg_date_range_type": flow.date_range_type,
                "trg_date_range_mode": flow.date_range_mode,
            }
            if flow.automation_id:
                flow.automation_id.write(automation_vals)
            else:
                flow.automation_id = self.env["base.automation"].create(automation_vals)
            automation = flow.automation_id
            if not automation.action_server_ids:
                self.env["ir.actions.server"].create({
                    "name": self.env._("Start the flow %s", flow.name),
                    "model_id": flow.model_id.id,
                    "state": "angels_flow",
                    "angels_flow_id": flow.id,
                    "usage": "base_automation",
                    "base_automation_id": automation.id,
                })
            else:
                automation.action_server_ids.write({"model_id": flow.model_id.id})

    def _records_domain(self):
        self.ensure_one()
        return safe_eval(self.filter_domain or "[]", {
            "uid": self.env.uid,
            "user": self.env.user,
            "context_today": lambda: fields.Date.context_today(self),
            "datetime": safe_eval_datetime,
            "relativedelta": relativedelta,
        })

    def _start(self, records, raise_errors=True):
        """Start a run of the flow on each of ``records`` that may go through it.

        Started automatically (``raise_errors`` False), a run that fails is
        cancelled with the reason in its chatter: it never blocks the change
        that started it.
        """
        self.ensure_one()
        Run = self.env["angels.flow.run"].sudo()
        starting = self.env.context.get("angels_flow_starting", ())
        if not self.active or not records or self.id in starting:
            # A change made while the flow starts does not start it again.
            return Run
        self = self.with_context(angels_flow_starting=(*starting, self.id))
        Run = Run.with_context(angels_flow_starting=(*starting, self.id))
        records = records.sudo().filtered_domain(self._records_domain())
        # A draft run is one being started.
        busy_states = ("draft", "pending", "approved", "rejected") if self.once_per_record else ("draft", "pending")
        busy = set(Run.search([
            ("flow_id", "=", self.id), ("res_id", "in", records.ids), ("state", "in", busy_states),
        ]).mapped("res_id"))
        start = self._start_node()
        runs = Run
        for record in records.filtered(lambda r: r.id not in busy):
            run = Run.create({
                "flow_id": self.id,
                "res_model": self.model_name,
                "res_id": record.id,
                "user_id": self.env.uid,
                "company_id": (record.company_id.id if "company_id" in record._fields else False) or self.env.company.id,
            })
            runs |= run
            if raise_errors:
                run._flow_start(start)
                continue
            try:
                with self.env.cr.savepoint():
                    run._flow_start(start)
            except UserError as error:
                _logger.info("Flow %s could not start on %s: %s", self.name, record, error)
                run._flow_fail(error)
        return runs

    def _start_node(self):
        self.ensure_one()
        return self.node_ids.filtered(lambda n: n.node_type == "start")[:1]

    def _next_run_after(self, moment):
        self.ensure_one()
        return moment + relativedelta(**{self.interval_type: self.interval_number})

    @api.model
    def _cron_run(self):
        """Scheduled flows whose time has come, and runs whose wait is over."""
        now = fields.Datetime.now()
        for flow in self.search([("trigger", "=", "scheduled"), ("next_run", "<=", now)]):
            records = self.env[flow.model_name].sudo().search(flow._records_domain())
            flow._start(records, raise_errors=False)
            next_run = flow.next_run or now
            while next_run <= now:
                next_run = flow._next_run_after(next_run)
            flow.next_run = next_run
        self.env["angels.flow.run"]._cron_resume()
        # Late steps of every model built on flows (runs, form requests...).
        for model in self.env.registry["angels.flow.step.mixin"]._inherit_children:
            if not self.env[model]._abstract:
                self.env[model]._flow_check_deadlines()

    def action_start_now(self):
        """Start the flow now on every record it applies to."""
        self.ensure_one()
        records = self.env[self.model_name].search(self._records_domain())
        runs = self._start(records)
        return _notification(
            _("The flow started on %(count)s records.", count=len(runs)) if runs
            else _("No record can start the flow now."),
            "success" if runs else "warning",
        )

    # ------------------------------------------------------------------
    # Getting started
    # ------------------------------------------------------------------

    @api.model
    def get_welcome_data(self):
        """The examples to start from, for the Get Started screen."""
        self.check_access("create")
        examples = self.with_context(active_test=False).search([("is_example", "=", True)])
        triggers = dict(self._fields["trigger"]._description_selection(self.env))
        return {
            "examples": [{
                "id": flow.id,
                "name": flow.name,
                "description": flow.description or "",
                "model": flow.model_id.name,
                "trigger": triggers[flow.trigger],
                "active": flow.active,
                "steps": len(flow.node_ids) - 1,
            } for flow in examples],
            "flow_count": self.search_count([("is_example", "=", False)]),
        }

    def action_use_example(self):
        """A copy of the example, to make it one's own; it opens in the designer."""
        self.ensure_one()
        copy = self.copy({"active": False})
        return copy.action_open_designer()

    def action_activate(self):
        self.write({"active": True})
        return True

    def action_open_designer(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "angels_flow_designer",
            "name": self.name,
            "context": {"active_id": self.id},
        }

    def action_view_runs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Runs"),
            "res_model": "angels.flow.run",
            "views": [[False, "list"], [False, "form"]],
            "domain": [("flow_id", "=", self.id)],
            "context": {"default_flow_id": self.id},
        }

    # ------------------------------------------------------------------
    # Designer
    # ------------------------------------------------------------------

    def _condition_fields(self):
        self.ensure_one()
        return self.env["ir.model.fields"].sudo().search([
            ("model_id", "=", self.model_id.id), ("store", "=", True),
            ("name", "not in", ("id", "create_uid", "write_uid", "__last_update")),
        ]).filtered(field_kind).sorted(lambda f: f.field_description.lower())

    def get_design_data(self):
        self.ensure_one()
        self.check_access("write")
        Model = self.env[self.model_name]
        sources = []
        for field in self._condition_fields():
            source = {"id": field.id, "name": field.field_description, "type": field_kind(field)}
            if field.ttype == "selection":
                selection = Model._fields[field.name]._description_selection(self.env) if field.name in Model._fields else []
                source["options"] = [{"value": key, "label": label} for key, label in selection]
            sources.append(source)
        users = [{"id": s["id"], "name": s["name"]} for s in sources if s["type"] == "user"]
        update_fields = []
        for field in self._update_fields():
            item = {"id": field.id, "name": field.field_description, "type": field.ttype,
                    "relation": field.relation or False, "required": field.required}
            if field.ttype == "selection" and field.name in Model._fields:
                item["options"] = [{"value": key, "label": label}
                                   for key, label in Model._fields[field.name]._description_selection(self.env)]
            update_fields.append(item)
        return {
            "flow": {
                "id": self.id, "name": self.name, "model": self.model_id.name, "model_name": self.model_name,
                "active": self.active, "is_example": self.is_example,
                "trigger": self.trigger,
                "trigger_label": dict(self._fields["trigger"]._description_selection(self.env))[self.trigger],
            },
            "nodes": [node._to_client() for node in self.node_ids],
            "ports": self.env["angels.flow.node"]._flow_ports(),
            "sources": sources,
            "user_sources": users,
            "update_fields": update_fields,
            "action_choices": self._flow_action_choices(),
            "update_sources": dict(self.env["angels.flow.update"]._fields["source"]._description_selection(self.env)),
            "operators_by_type": OPERATORS_BY_TYPE,
            "labels": {
                "node_types": dict(self.env["angels.flow.node"]._fields["node_type"]._description_selection(self.env)),
                "operators": dict(self.env["angels.flow.condition"]._fields["operator"]._description_selection(self.env)),
            },
        }

    def save_design(self, data):
        """Save the steps of the flow as the designer sends them; return the new design."""
        self.ensure_one()
        self.check_access("write")
        Node = self.env["angels.flow.node"].with_context(**{DEFER: True})
        fields_by_id = {f.id: f for f in self._condition_fields()}
        current = self.node_ids
        nodes_by_client_id = {}
        for item in data.get("nodes", []):
            vals = {key: item[key] for key in NODE_KEYS if key in item}
            vals.update({
                "node_type": item.get("type") or "approve",
                "pos_x": int(item.get("x") or 0),
                "pos_y": int(item.get("y") or 0),
                "color": int(item.get("color") or 0),
                "user_ids": [fields.Command.set(item.get("user_ids") or [])],
                "group_id": item.get("group_id") or False,
                "escalate_user_id": item.get("escalate_user_id") or False,
                "user_field_id": item.get("user_field_id") if item.get("user_field_id") in fields_by_id else False,
                "condition_match": item.get("match") or "all",
            })
            node = current.filtered(lambda n, cid=item.get("id"): n.id == cid)
            if node:
                node.with_context(**{DEFER: True}).write(vals)
            else:
                node = Node.create(dict(vals, flow_id=self.id))
            nodes_by_client_id[item.get("id")] = node
        (current - Node.union(*nodes_by_client_id.values())).unlink()
        ports = Node._flow_ports()
        for item in data.get("nodes", []):
            node = nodes_by_client_id[item.get("id")]
            links = item.get("links") or {}
            vals = {name: False for name in PORT_FIELDS.values()}
            for port in ports[node.node_type]:
                target = nodes_by_client_id.get(links.get(port))
                vals[PORT_FIELDS[port]] = target.id if target else False
            conditions = [c for c in item.get("conditions") or [] if c.get("source_id") in fields_by_id]
            vals["condition_ids"] = [fields.Command.clear()] + [
                fields.Command.create({"field_id": c["source_id"], "operator": c.get("operator") or "=",
                                       "value": c.get("value") or False})
                for c in conditions
            ] if node.node_type == "condition" else [fields.Command.clear()]
            allowed = {f.id for f in self._update_fields()}
            vals["update_ids"] = [fields.Command.clear()] + [
                fields.Command.create({"sequence": index, "field_id": u["field_id"], "source": u.get("source") or "value",
                                       "value": u.get("value") or False, "days": int(u.get("days") or 0)})
                for index, u in enumerate(item.get("updates") or []) if u.get("field_id") in allowed
            ] if node.node_type == "update" else [fields.Command.clear()]
            node.write(vals)
        if len(self.node_ids.filtered(lambda n: n.node_type == "start")) != 1:
            raise ValidationError(_("A flow has exactly one Start."))
        # Every check that waited for the whole flow.
        self.node_ids._check_recipients()
        self.node_ids._check_step_settings()
        self.node_ids._check_action()
        self.node_ids._check_deadline()
        return self.get_design_data()


class AngelsFlowNode(models.Model):
    _name = "angels.flow.node"
    _inherit = ["angels.flow.node.mixin"]
    _description = "Flow Step"
    _order = "flow_id, id"
    _flow_container = "flow_id"

    flow_id = fields.Many2one("angels.flow", required=True, ondelete="cascade", index=True)
    node_type = fields.Selection(selection_add=[("notify",), ("wait", "Wait")], ondelete={"wait": "cascade"})
    next_id = fields.Many2one("angels.flow.node", string="Then", ondelete="set null")
    yes_id = fields.Many2one("angels.flow.node", string="If Yes", ondelete="set null")
    no_id = fields.Many2one("angels.flow.node", string="If No", ondelete="set null")
    reject_id = fields.Many2one(
        "angels.flow.node", string="If Rejected", ondelete="set null",
        help="Where a rejected run goes. Empty: the run is rejected.",
    )
    expired_id = fields.Many2one(
        "angels.flow.node", string="If Expired", ondelete="set null",
        help="Where a late step goes when its deadline says so. Empty: the run is rejected.",
    )
    assign_type = fields.Selection(
        selection_add=[("field", "User in a field of the record")], ondelete={"field": "set default"},
    )
    user_field_id = fields.Many2one(
        "ir.model.fields", string="User Field", ondelete="set null",
        domain="[('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
    )
    wait_amount = fields.Integer(string="Wait", default=1)
    wait_unit = fields.Selection([("hours", "Hours"), ("days", "Days")], string="Wait Unit", default="days")
    condition_ids = fields.One2many("angels.flow.condition", "node_id", string="Conditions", copy=False)

    @api.model
    def _flow_ports(self):
        ports = {kind: outputs for kind, outputs in super()._flow_ports().items() if kind != "back"}
        return {**ports, "wait": ("next",)}

    @api.constrains("next_id", "yes_id", "no_id", "reject_id", "expired_id", "flow_id")
    def _check_links(self):
        self._check_flow_links()

    @api.constrains("node_type", "assign_type", "user_field_id", "wait_amount")
    def _check_step_settings(self):
        if self.env.context.get(DEFER):
            return
        for node in self:
            if node.node_type == "back":
                raise ValidationError(_("A flow on records has no step back to a requester."))
            if node.node_type == "wait" and node.wait_amount < 1:
                raise ValidationError(_("The step %(step)s waits at least 1 hour or day.", step=node.name))
            if node.node_type in ("approve", "task", "notify") and node.assign_type == "field" and (
                node.user_field_id.model != node.flow_id.model_name
            ):
                raise ValidationError(_("The step %(step)s needs a user field of the record.", step=node.name))

    def _flow_condition_met(self, values):
        self.ensure_one()
        if not self.condition_ids:
            return True
        results = (condition._matches(values) for condition in self.condition_ids)
        return all(results) if self.condition_match == "all" else any(results)

    def _get_recipients(self, values):
        self.ensure_one()
        if self.assign_type != "field":
            return super()._get_recipients(values)
        users = self.env["res.users"].browse(values.get(self.user_field_id.name) or [])
        return users.sudo().exists().filtered(lambda u: u.active and not u.share)

    def _to_client(self):
        data = super()._to_client()
        data.update({
            "user_field_id": self.user_field_id.id,
            "wait_amount": self.wait_amount,
            "wait_unit": self.wait_unit or "days",
            "conditions": [condition._to_client() for condition in self.condition_ids],
        })
        return data


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(selection_add=[("angels_flow", "Start a Flow")], ondelete={"angels_flow": "cascade"})
    angels_flow_id = fields.Many2one("angels.flow", string="Flow", ondelete="cascade", index="btree_not_null")

    def _run_action_angels_flow_multi(self, eval_context=None):
        model = eval_context["model"]
        records = (eval_context.get("records") or model.browse()) | (eval_context.get("record") or model.browse())
        automatic = self.usage == "base_automation"
        runs = self.angels_flow_id._start(records, raise_errors=not automatic)
        if automatic:
            return False
        return _notification(
            _("The flow %(flow)s started.", flow=self.angels_flow_id.name) if runs
            else _("The flow %(flow)s cannot start on this record: it is not in the flow's records, "
                   "or it already went through it.", flow=self.angels_flow_id.name),
            "success" if runs else "warning",
        )


def _notification(message, kind):
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {"message": message, "type": kind, "sticky": False},
    }
