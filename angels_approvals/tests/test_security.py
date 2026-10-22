from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ApprovalCase


@tagged("post_install", "-at_install")
class TestApprovalSecurity(ApprovalCase):

    def test_visibility(self):
        request = self.submit()
        self.decide(request, self.approver_a)
        Request = self.env["angels.approval.request"]
        self.assertIn(request, Request.with_user(self.requester).search([]))
        self.assertIn(request, Request.with_user(self.approver_a).search([]))
        self.assertNotIn(request, Request.with_user(self.outsider).search([]))
        self.assertIn(request, Request.with_user(self.manager).search([]))
        with self.assertRaises(AccessError):
            request.with_user(self.outsider).read(["name"])
        with self.assertRaises(AccessError):
            request.decision_ids.with_user(self.outsider).read(["comment"])

    def test_users_cannot_forge_state(self):
        request = self.submit()
        with self.assertRaises(AccessError):
            request.with_user(self.requester).write({"state": "approved"})
        with self.assertRaises(UserError):
            request.with_user(self.manager).write({"state": "approved"})
        with self.assertRaises(AccessError):
            self.env["angels.approval.request"].with_user(self.requester).create({
                "flow_id": self.flow.id, "res_model": "res.partner",
                "res_id": self.partner.id, "requested_by_id": self.requester.id,
            })
        with self.assertRaises(AccessError):
            request.line_ids.with_user(self.approver_a).write({"state": "approved"})

    def test_decisions_are_immutable(self):
        request = self.submit()
        self.decide(request, self.approver_a, comment="fine")
        decision = request.decision_ids
        with self.assertRaises(UserError):
            decision.sudo().comment = "changed"
        with self.assertRaises(UserError):
            decision.sudo().unlink()
        with self.assertRaises(UserError):
            request.sudo().unlink()

    def test_configuration_needs_manager(self):
        with self.assertRaises(AccessError):
            self.flow.with_user(self.requester).name = "Mine"
        self.flow.with_user(self.manager).name = "Renamed"
        with self.assertRaises(AccessError):
            self.flow.with_user(self.manager).read(["approve_action_id"])

    def test_requester_needs_read_access_to_record(self):
        company = self.env["res.company"].create({"name": "Other Co"})
        hidden = self.env["res.partner"].create({
            "name": "Hidden Co", "is_company": True, "company_id": company.id,
        })
        with self.assertRaises(AccessError):
            self.submit(record=hidden)

    def test_cron_reminds_and_escalates(self):
        self.flow.step_ids[0].escalation_user_id = self.manager
        request = self.submit()
        line = request.line_ids[0]
        line.sudo().deadline = fields.Date.today() - timedelta(days=1)
        self.env["angels.approval.request.line"]._process_overdue()
        self.assertIn(self.manager, line.approver_ids)
        self.assertTrue(line.escalated and line.last_reminder == fields.Date.today())
        self.assertTrue(request.with_user(self.manager).is_my_turn)
        messages = len(request.message_ids)
        self.env["angels.approval.request.line"]._process_overdue()
        self.assertEqual(len(request.message_ids), messages, "one reminder per day")
