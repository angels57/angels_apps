from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccountFlow(TransactionCase):

    def test_overdue_invoices_example(self):
        example = self.env.ref("angels_flow_account.example_flow_overdue_invoices")
        self.assertEqual((example.enabled, example.trigger, example.interval_type), (False, "scheduled", "weeks"))
        # The filter reads today's date.
        self.assertIn(("state", "=", "posted"), example._records_domain())
        self.assertTrue(any(isinstance(term, tuple) and term[0] == "invoice_date_due" for term in example._records_domain()))
        self.assertEqual(len(example.node_ids), 7)
        self.assertEqual(example._start_node().next_id.node_type, "notify")
        unpaid = example.node_ids.filtered(lambda n: n.node_type == "condition").condition_ids
        self.assertEqual((unpaid.field_id.name, unpaid.value), ("payment_state", "not_paid"))
        example.action_activate()
        example.next_run = fields.Datetime.now() - timedelta(minutes=1)
        self.env["angels.flow"]._cron_run()
        self.assertGreater(example.next_run, fields.Datetime.now() + timedelta(days=6))
