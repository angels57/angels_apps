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

    def test_update_record_and_server_action(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        field = self.env["ir.model.fields"]._get
        server = self.env["ir.actions.server"].create({
            "name": "Mark as Checked", "model_id": self.partner_model.id, "state": "code",
            "code": "record.write({'ref': 'CHECKED'})",
        })
        choices = {c["key"]: c for c in flow._flow_action_choices()}
        self.assertIn(f"server:{server.id}", choices)
        self.assertNotIn(f"server:{flow.action_id.id}", choices, "not the flow's own start action")
        Node = self.env["angels.flow.node"]
        action = Node.create({"flow_id": flow.id, "name": "Check", "node_type": "action",
                              "action_ref": f"server:{server.id}", "next_id": approve.next_id.id})
        update = Node.create({
            "flow_id": flow.id, "name": "Fill", "node_type": "update", "next_id": action.id,
            "update_ids": [
                fields.Command.create({"field_id": field("res.partner", "comment").id, "value": "Checked by the flow"}),
                fields.Command.create({"field_id": field("res.partner", "user_id").id, "source": "starter"}),
                fields.Command.create({"field_id": field("res.partner", "is_company").id, "value": "true"}),
                fields.Command.create({"field_id": field("res.partner", "website").id, "source": "empty"}),
            ],
        })
        approve.next_id = update
        partner = self.env["res.partner"].create({"name": "Gil", "website": "https://gil.example.com"})
        run = flow.with_user(self.seller)._start(partner)
        run.with_user(self.boss).current_step_id._decide("approve")
        self.assertEqual(run.state, "approved")
        self.assertIn("Checked by the flow", partner.comment)
        self.assertEqual((partner.user_id, partner.is_company, partner.website, partner.ref),
                         (self.seller, True, False, "CHECKED"))
        deadline = self.env["angels.flow.update"].new({
            "field_id": field("mail.activity", "date_deadline").id, "source": "today", "days": 7,
        })
        self.assertEqual(deadline._compute_value(run), fields.Date.context_today(run) + timedelta(days=7))

    def test_failing_action_stops_with_the_step_name(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        server = self.env["ir.actions.server"].create({
            "name": "Fail", "model_id": self.partner_model.id, "state": "code",
            "code": "raise UserError('No way')",
        })
        action = self.env["angels.flow.node"].create({"flow_id": flow.id, "name": "Try", "node_type": "action",
                                                      "action_ref": f"server:{server.id}"})
        flow._start_node().next_id = action
        partner = self.env["res.partner"].create({"name": "Hal"})
        with self.assertRaisesRegex(UserError, "Try could not finish: No way"):
            flow._start(partner)
        with self.assertRaises(ValidationError):
            action.action_ref = "button:unlink"

    def late(self, run):
        run.current_step_id.sudo().date_deadline = fields.Datetime.now() - timedelta(minutes=1)
        self.env["angels.flow"]._cron_run()

    def test_deadline_reminds_then_escalates(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        approve.write({"deadline_amount": 2, "deadline_unit": "days"})
        run = flow._start(self.env["res.partner"].create({"name": "Ida"}))
        step = run.current_step_id
        self.assertAlmostEqual(step.date_deadline, fields.Datetime.now() + timedelta(days=2), delta=timedelta(minutes=5))
        self.assertEqual(run.activity_ids.date_deadline, fields.Date.to_date(step.date_deadline))
        self.late(run)
        self.assertTrue(step.is_late)
        self.assertIn("is late: please act on it", run.message_ids[0].body)
        self.env["angels.flow"]._cron_run()
        self.assertEqual(len(run.message_ids.filtered(lambda m: "is late" in (m.body or ""))), 1, "reminded once")

        approve.write({"on_deadline": "escalate", "escalate_user_id": self.seller.id})
        run = flow._start(self.env["res.partner"].create({"name": "Joe"}))
        self.late(run)
        self.assertEqual(run.current_step_id.user_ids, self.boss | self.seller)
        self.assertIn(self.seller, run.activity_ids.user_id)
        run.with_user(self.seller).current_step_id._decide("approve")
        self.assertEqual(run.state, "approved")

    def test_deadline_expires_by_its_output(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        approve.write({"deadline_amount": 4, "deadline_unit": "hours", "on_deadline": "expire"})
        self.assertIn("expired", flow.get_design_data()["ports"]["approve"])
        run = flow._start(self.env["res.partner"].create({"name": "Kim"}))
        self.late(run)
        self.assertEqual((run.step_ids.state, run.state), ("expired", "rejected"), "no Expired link: rejected")
        notify = self.env["angels.flow.node"].create({
            "flow_id": flow.id, "name": "Tell the Seller", "node_type": "notify",
            "user_ids": [fields.Command.set(self.seller.ids)],
        })
        approve.expired_id = notify
        run = flow._start(self.env["res.partner"].create({"name": "Lou"}))
        self.late(run)
        self.assertEqual(run.state, "approved", "Expired → notify → end of the flow")
        self.assertEqual(run.step_ids.mapped("state"), ["expired", "notified"])
        with self.assertRaises(ValidationError):
            approve.write({"on_deadline": "escalate", "escalate_user_id": False})

    def test_trail_and_times(self):
        flow = self.make_flow(trigger="manual", domain="[]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        run = flow._start(self.env["res.partner"].create({"name": "Max"}))
        data = run.get_flow_trail()
        self.assertEqual([e["node"] for e in data["trail"]], [flow._start_node().id, approve.id])
        self.assertEqual(data["current"], approve.id)
        self.assertEqual(len(data["nodes"]), 3)
        run.with_user(self.boss).current_step_id._decide("approve")
        data = run.get_flow_trail()
        self.assertEqual(len(data["trail"]), 3)
        self.assertFalse(data["current"])
        self.assertEqual(data["trail"][1]["state"], "approved")
        stats = flow.get_step_stats()
        self.assertEqual(stats[approve.id]["count"], 1)

    def test_simulation_changes_nothing(self):
        flow = self.make_flow(trigger="manual", domain="[('is_company', '=', True)]")
        approve = flow.node_ids.filtered(lambda n: n.node_type == "approve")
        Node = self.env["angels.flow.node"]
        update = Node.create({
            "flow_id": flow.id, "name": "Mark", "node_type": "update", "next_id": approve.next_id.id,
            "update_ids": [fields.Command.create({
                "field_id": self.env["ir.model.fields"]._get("res.partner", "comment").id, "value": "Done",
            })],
        })
        approve.next_id = update
        partner = self.env["res.partner"].create({"name": "Ned"})
        result = flow.simulate(partner.id)
        self.assertFalse(result["matches"], "not a company")
        self.assertEqual([e["node"] for e in result["path"]], [flow._start_node().id, approve.id, update.id,
                                                              update.next_id.id])
        self.assertIn("Boss", result["path"][1]["text"])
        self.assertIn("Would set", result["path"][2]["text"])
        self.assertFalse(partner.comment)
        self.assertFalse(flow.run_ids)

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
