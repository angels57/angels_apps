from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ApprovalCase


@tagged("post_install", "-at_install")
class TestApprovalFlow(ApprovalCase):

    def test_two_steps_in_order(self):
        request = self.submit()
        sales, finance = request.line_ids.sorted("sequence")
        self.assertEqual((request.state, sales.state, finance.state), ("pending", "pending", "waiting"))
        self.assertTrue(request.with_user(self.approver_a).is_my_turn)
        self.assertFalse(request.with_user(self.approver_b).is_my_turn)
        with self.assertRaises(AccessError):
            self.decide(request, self.approver_b)
        self.decide(request, self.approver_a)
        self.assertEqual((sales.state, finance.state), ("approved", "pending"))
        self.assertEqual(request.current_line_id, finance)
        self.decide(request, self.approver_b, comment="OK")
        self.assertEqual(request.state, "approved")
        self.assertEqual(len(request.decision_ids), 2)
        self.assertFalse(request.activity_ids)
        self.assertIn(request.name, self.partner.message_ids[0].body)

    def test_activities_scheduled_for_approvers(self):
        request = self.submit()
        self.assertEqual(request.activity_ids.user_id, self.approver_a)
        self.assertEqual(
            request.activity_ids.activity_type_id,
            self.env.ref("angels_approvals.mail_activity_approval"),
        )

    def test_reject_needs_reason_and_finishes(self):
        request = self.submit()
        with self.assertRaises(UserError):
            self.decide(request, self.approver_a, "reject")
        self.decide(request, self.approver_a, "reject", comment="Too risky")
        self.assertEqual(request.state, "rejected")
        self.assertEqual(request.line_ids.mapped("state"), ["rejected", "skipped"])
        with self.assertRaises(UserError):
            request.line_ids[0].with_user(self.approver_a)._decide("approve")

    def test_all_rule_needs_every_approver(self):
        step = self.flow.step_ids[0]
        step.write({"approval_rule": "all", "user_ids": [(6, 0, (self.approver_a | self.approver_b).ids)]})
        request = self.submit()
        self.decide(request, self.approver_a)
        self.assertEqual(request.line_ids[0].state, "pending")
        self.assertFalse(request.with_user(self.approver_a).is_my_turn)
        self.decide(request, self.approver_b)
        self.assertEqual(request.line_ids[0].state, "approved")

    def test_condition_skips_step(self):
        self.flow.step_ids[1].condition_domain = "[('name', 'ilike', 'huge')]"
        request = self.submit()
        self.assertEqual(request.line_ids.mapped("state"), ["pending", "skipped"])
        self.decide(request, self.approver_a)
        self.assertEqual(request.state, "approved")

    def test_group_and_field_approvers(self):
        group = self.env["res.groups"].create({"name": "Approval testers"})
        group.user_ids = self.approver_b
        self.flow.step_ids[0].write({"approver_type": "field",
                                     "user_field_id": self.env["ir.model.fields"]._get("res.partner", "user_id").id})
        self.flow.step_ids[1].write({"approver_type": "group", "group_id": group.id})
        self.partner.user_id = self.approver_a
        request = self.submit()
        self.assertEqual(request.line_ids[0].approver_ids, self.approver_a)
        self.decide(request, self.approver_a)
        self.assertEqual(request.line_ids[1].approver_ids, self.approver_b)

    def test_missing_approver_blocks_submit(self):
        self.flow.step_ids[0].write({"approver_type": "field",
                                     "user_field_id": self.env["ir.model.fields"]._get("res.partner", "user_id").id})
        with self.assertRaises(UserError):
            self.submit()

    def test_self_approval(self):
        self.flow.step_ids[0].user_ids = self.requester
        request = self.submit()
        with self.assertRaises(UserError):
            self.decide(request, self.requester)
        self.flow.allow_self_approval = True
        self.decide(request, self.requester)
        self.assertEqual(request.line_ids[0].state, "approved")

    def test_one_pending_request_per_record(self):
        self.submit()
        with self.assertRaises(Exception), self.cr.savepoint(), mute_logger("odoo.sql_db"):
            self.submit()

    def test_cancel(self):
        request = self.submit()
        with self.assertRaises(AccessError):
            request.with_user(self.approver_a).action_cancel()
        request.with_user(self.requester).action_cancel()
        self.assertEqual(request.state, "cancelled")
        self.assertFalse(request.activity_ids)
        self.submit()  # a new request is allowed after cancelling

    def test_flow_domain_filters_records(self):
        person = self.env["res.partner"].create({"name": "Someone"})
        wizard = self.env["angels.approval.request.wizard"].with_user(self.requester).with_context(
            active_model="res.partner", active_ids=person.ids,
        ).create({})
        self.assertFalse(wizard.available_flow_ids)
        wizard.flow_id = self.flow
        with self.assertRaises(UserError):
            wizard.action_submit()

    def test_requester_groups(self):
        self.flow.requester_group_ids = self.env.ref("angels_approvals.group_approval_manager")
        with self.assertRaises(UserError):
            self.submit()
        request = self.submit(user=self.manager)
        self.assertEqual(request.requested_by_id, self.manager)

    def test_server_actions(self):
        action = self.env["ir.actions.server"].create({
            "name": "Mark approved",
            "model_id": self.partner_model.id,
            "state": "code",
            "code": "record.write({'comment': 'approved by flow'})",
        })
        self.flow.approve_action_id = action
        request = self.submit()
        self.decide(request, self.approver_a)
        self.decide(request, self.approver_b)
        self.assertIn("approved by flow", self.partner.comment)

    def test_bound_actions_follow_flows(self):
        Action = self.env["ir.actions.act_window"]
        domain = [("binding_model_id", "=", self.partner_model.id),
                  ("res_model", "in", ("angels.approval.request.wizard", "angels.approval.request"))]
        self.assertEqual(Action.search_count(domain), 2)
        self.flow.active = False
        self.assertEqual(Action.search_count(domain), 0)
        self.flow.active = True
        self.assertEqual(Action.search_count(domain), 2)

    def test_invalid_configuration(self):
        with self.assertRaises(ValidationError):
            self.flow.domain = "[('no_such_field', '=', 1)]"
        with self.assertRaises(ValidationError):
            self.flow.step_ids[0].user_ids = False
