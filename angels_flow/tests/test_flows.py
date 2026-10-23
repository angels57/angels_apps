from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, new_test_user, tagged

from odoo.addons.angels_flow.models.flow_node import DEFER


@tagged("post_install", "-at_install")
class TestFlows(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.boss = new_test_user(cls.env, "flow_boss", groups="base.group_user", name="Boss")
        cls.seller = new_test_user(cls.env, "flow_seller", groups="base.group_user,base.group_partner_manager",
                                   name="Seller")
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.is_company = cls.env["ir.model.fields"]._get("res.partner", "is_company")
        cls.salesperson = cls.env["ir.model.fields"]._get("res.partner", "user_id")

    def make_flow(self, trigger="on_create", domain="[('is_company', '=', True)]", **vals):
        """Start → approval by the boss → end."""
        flow = self.env["angels.flow"].create(dict({
            "name": "Company Check", "model_id": self.partner_model.id, "trigger": trigger, "filter_domain": domain,
        }, **vals))
        Node = self.env["angels.flow.node"].with_context(**{DEFER: True})
        approve = Node.create({"flow_id": flow.id, "name": "Boss Approval", "node_type": "approve",
                               "user_ids": [fields.Command.set(self.boss.ids)]})
        end = Node.create({"flow_id": flow.id, "name": "Approved", "node_type": "end"})
        approve.next_id = end
        flow._start_node().next_id = approve
        return flow

    def test_created_record_starts_the_flow_and_approval_ends_it(self):
        flow = self.make_flow()
        company = self.env["res.partner"].with_user(self.seller).create({"name": "Acme", "is_company": True})
        run = flow.run_ids
        self.assertEqual((len(run), run.state, run.res_id), (1, "pending", company.id))
        self.assertTrue(run.name.startswith("FLOW/"))
        self.assertEqual(run.current_step_id.user_ids, self.boss)
        self.assertEqual(run.activity_ids.user_id, self.boss)
        self.assertTrue(run.with_user(self.boss).is_my_turn)
        self.assertIn(run, self.env["angels.flow.run"].with_user(self.boss).search([("is_my_turn", "=", True)]))
        run.with_user(self.boss).current_step_id._decide("approve", "Fine")
        self.assertEqual(run.state, "approved")
        self.assertFalse(run.activity_ids)
        self.assertIn("ended: approved", company.message_ids[0].body)
        self.assertIn("started", company.message_ids[1].body)

    def test_self_approval(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        partner = self.env["res.partner"].create({"name": "Fay"})
        run = flow.with_user(self.boss).sudo()._start(partner).with_user(self.boss)
        with self.assertRaisesRegex(UserError, "your own"):
            run.current_step_id._decide("approve")
        flow.allow_self_approval = True
        run.current_step_id._decide("approve")
        self.assertEqual(run.state, "approved")

    def test_only_matching_records_and_once_each(self):
        flow = self.make_flow(trigger="on_create_or_write")
        person = self.env["res.partner"].create({"name": "Ann"})
        self.assertFalse(flow.run_ids, "not a company")
        person.is_company = True
        self.assertEqual(len(flow.run_ids), 1, "it matches once updated")
        flow.run_ids.with_user(self.boss).current_step_id._decide("approve")
        person.name = "Ann Ltd"
        self.assertEqual(len(flow.run_ids), 1, "once per record")
        flow.once_per_record = False
        person.name = "Ann Inc"
        self.assertEqual(len(flow.run_ids), 2, "again once the last run is over")

    def test_manual_start_from_the_action_menu(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        self.assertEqual(flow.action_id.binding_model_id, self.partner_model)
        self.assertFalse(flow.automation_id)
        partner = self.env["res.partner"].create({"name": "Bob"})
        self.assertFalse(flow.run_ids, "a manual flow does not start by itself")
        result = flow.action_id.with_context(active_model="res.partner", active_ids=partner.ids).run()
        self.assertEqual(result["params"]["type"], "success")
        self.assertEqual(flow.run_ids.res_id, partner.id)
        result = flow.action_id.with_context(active_model="res.partner", active_ids=partner.ids).run()
        self.assertEqual(result["params"]["type"], "warning", "already running")
        flow.active = False
        self.assertFalse(flow.action_id.binding_model_id)

    def test_scheduled_flow(self):
        flow = self.make_flow(trigger="scheduled", domain="[('name', '=like', 'Sched%')]",
                              interval_number=1, interval_type="weeks", once_per_record=False)
        partners = self.env["res.partner"].create([{"name": "Sched A"}, {"name": "Sched B"}])
        flow.next_run = fields.Datetime.now() - timedelta(minutes=1)
        self.env["angels.flow"]._cron_run()
        self.assertEqual(set(flow.run_ids.mapped("res_id")), set(partners.ids))
        self.assertGreater(flow.next_run, fields.Datetime.now() + timedelta(days=6))
        self.env["angels.flow"]._cron_run()
        self.assertEqual(len(flow.run_ids), 2, "not due yet")

    def test_wait_then_go_on(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        Node = self.env["angels.flow.node"]
        wait = Node.create({"flow_id": flow.id, "name": "Two Hours", "node_type": "wait",
                            "wait_amount": 2, "wait_unit": "hours"})
        end = Node.create({"flow_id": flow.id, "name": "Done", "node_type": "end"})
        wait.next_id = end
        flow._start_node().next_id = wait
        partner = self.env["res.partner"].create({"name": "Carl"})
        run = flow._start(partner)
        self.assertEqual((run.state, run.wait_node_id), ("pending", wait))
        self.assertGreater(run.wait_until, fields.Datetime.now() + timedelta(minutes=100))
        self.env["angels.flow.run"]._cron_resume()
        self.assertEqual(run.state, "pending", "still waiting")
        run.sudo().wait_until = fields.Datetime.now() - timedelta(minutes=1)
        self.env["angels.flow.run"]._cron_resume()
        self.assertEqual((run.state, run.wait_until), ("approved", False))

    def test_condition_and_user_field_of_the_record(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        approve.write({"assign_type": "field", "user_field_id": self.salesperson.id})
        Node = self.env["angels.flow.node"]
        end_no = Node.create({"flow_id": flow.id, "name": "Not a Company", "node_type": "end", "end_state": "rejected"})
        condition = Node.create({
            "flow_id": flow.id, "name": "Company?", "node_type": "condition",
            "yes_id": approve.id, "no_id": end_no.id,
            "condition_ids": [fields.Command.create({"field_id": self.is_company.id, "operator": "=", "value": "1"})],
        })
        flow._start_node().next_id = condition
        person, company = self.env["res.partner"].create([
            {"name": "Dan"}, {"name": "Dan Corp", "is_company": True, "user_id": self.seller.id},
        ])
        self.assertEqual(flow._start(person).state, "rejected")
        run = flow._start(company)
        self.assertEqual(run.current_step_id.user_ids, self.seller)

    def test_automatic_run_that_fails_does_not_block_the_change(self):
        flow = self.make_flow()
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        empty_group = self.env["res.groups"].create({"name": "Nobody"})
        approve.write({"assign_type": "group", "group_id": empty_group.id})
        company = self.env["res.partner"].create({"name": "Evil Corp", "is_company": True})
        self.assertTrue(company.exists())
        self.assertEqual(flow.run_ids.state, "cancelled")
        self.assertIn("Nobody can do the step", flow.run_ids.message_ids[0].body)

    def test_date_trigger_uses_an_automation_rule(self):
        date_field = self.env["ir.model.fields"]._get("res.partner", "write_date")
        flow = self.make_flow(trigger="on_time", date_field_id=date_field.id, date_range=3,
                              date_range_type="day", date_range_mode="after")
        automation = flow.automation_id
        self.assertEqual((automation.trigger, automation.trg_date_id, automation.trg_date_range,
                          automation.trg_date_range_mode), ("on_time", date_field, 3, "after"))
        self.assertEqual(automation.action_server_ids.angels_flow_id, flow)
        flow.trigger = "manual"
        self.assertFalse(flow.automation_id)
        self.assertFalse(automation.exists())

    def test_technical_models_are_refused(self):
        for model in ("ir.config_parameter", "angels.flow.run", "res.users.log"):
            with self.assertRaises(ValidationError, msg=model):
                self.env["angels.flow"].create({"name": "Bad", "model_id": self.env["ir.model"]._get(model).id})

    def test_designer_round_trip(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        data = flow.get_design_data()
        self.assertIn("wait", data["ports"])
        self.assertNotIn("back", data["ports"], "no requester to send back to")
        sources = {s["id"]: s for s in data["sources"]}
        self.assertEqual(sources[self.is_company.id]["type"], "boolean")
        self.assertIn(self.salesperson.id, [s["id"] for s in data["user_sources"]])
        start = next(n for n in data["nodes"] if n["type"] == "start")
        data["nodes"].append({
            "id": "new_1", "type": "wait", "name": "Pause", "x": 300, "y": 40, "links": {"next": start["links"]["next"]},
            "wait_amount": 3, "wait_unit": "days", "user_ids": [], "conditions": [],
        })
        start["links"]["next"] = "new_1"
        flow.save_design(data)
        wait = flow.node_ids.filtered(lambda n: n.node_type == "wait")
        self.assertEqual((wait.wait_amount, wait.wait_unit), (3, "days"))
        self.assertEqual(flow._start_node().next_id, wait)
        self.assertEqual(wait.next_id.node_type, "approve")

    def test_flow_form(self):
        with Form(self.env["angels.flow"]) as form:
            form.name = "Big Partners"
            form.model_id = self.partner_model
            form.trigger = "on_create"
        flow = form.save()
        self.assertEqual(flow.node_ids.node_type, "start")
        self.assertEqual(flow.automation_id.trigger, "on_create")
