from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import ApprovalCase


@tagged("post_install", "-at_install")
class TestApprovalDelegation(ApprovalCase):

    def delegate(self, user, delegate, days=3):
        today = fields.Date.today()
        return self.env["angels.approval.delegation"].with_user(user).create({
            "delegate_id": delegate.id,
            "date_from": today,
            "date_to": today + timedelta(days=days),
        })

    def test_delegate_approves_on_behalf(self):
        request = self.submit()
        self.delegate(self.approver_a, self.outsider)
        line = request.line_ids[0]
        self.assertIn(self.outsider, line.actor_ids)
        self.assertTrue(request.with_user(self.outsider).is_my_turn)
        self.assertIn(request, self.env["angels.approval.request"].with_user(self.outsider).search(
            [("is_my_turn", "=", True)]))
        self.decide(request, self.outsider)
        decision = request.decision_ids
        self.assertEqual((decision.user_id, decision.on_behalf_of_id), (self.outsider, self.approver_a))
        self.assertEqual(line.state, "approved")

    def test_delegation_before_submit_assigns_activity(self):
        self.delegate(self.approver_a, self.outsider)
        request = self.submit()
        self.assertEqual(request.activity_ids.user_id, self.outsider)

    def test_expired_delegation_does_not_count(self):
        request = self.submit()
        delegation = self.delegate(self.approver_a, self.outsider)
        delegation.sudo().active = False
        with self.assertRaises(AccessError):
            self.decide(request, self.outsider)

    def test_delegation_rules(self):
        with self.assertRaises(ValidationError):
            self.delegate(self.approver_a, self.approver_a)
        delegation = self.delegate(self.approver_a, self.outsider)
        with self.assertRaises(AccessError):
            delegation.with_user(self.approver_b).note = "hijack"
        with self.assertRaises(AccessError):
            self.env["angels.approval.delegation"].with_user(self.approver_b).create({
                "user_id": self.approver_a.id,
                "delegate_id": self.approver_b.id,
                "date_to": fields.Date.today(),
            })
        # The delegate can see it but not change it.
        delegation.with_user(self.outsider).read(["user_id"])
        with self.assertRaises(AccessError):
            delegation.with_user(self.outsider).date_to = fields.Date.today()
