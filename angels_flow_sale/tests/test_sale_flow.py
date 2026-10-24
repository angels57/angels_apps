from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.angels_flow.models.flow_node import DEFER


@tagged("post_install", "-at_install")
class TestSaleFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.manager = new_test_user(cls.env, "flow_sale_manager", groups="sales_team.group_sale_manager",
                                    name="Sales Manager")
        cls.customer = cls.env["res.partner"].create({"name": "Big Customer", "email": "big@example.com"})
        cls.product = cls.env["product.product"].create({"name": "Server", "list_price": 20000})
        cls.amount = cls.env["ir.model.fields"]._get("sale.order", "amount_total")

    def make_order(self, price=20000):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [fields.Command.create({"product_id": self.product.id, "price_unit": price})],
        })

    def test_big_quotation_approved_sent_and_confirmed(self):
        flow = self.env["angels.flow"].create({
            "name": "Big Quotations", "model_id": self.env["ir.model"]._get("sale.order").id,
            "trigger": "manual", "filter_domain": "[]",
        })
        keys = [choice["key"] for choice in flow._flow_action_choices()]
        self.assertIn("preset:sale_send", keys)
        self.assertIn("button:action_confirm", keys)
        Node = self.env["angels.flow.node"].with_context(**{DEFER: True})
        approve = Node.create({"flow_id": flow.id, "name": "Manager", "node_type": "approve",
                               "user_ids": [fields.Command.set(self.manager.ids)]})
        send = Node.create({"flow_id": flow.id, "name": "Send", "node_type": "action",
                            "action_ref": "preset:sale_send"})
        confirm = Node.create({"flow_id": flow.id, "name": "Confirm", "node_type": "action",
                               "action_ref": "button:action_confirm"})
        auto = Node.create({"flow_id": flow.id, "name": "Auto", "node_type": "end"})
        condition = Node.create({
            "flow_id": flow.id, "name": "Big?", "node_type": "condition", "yes_id": approve.id, "no_id": auto.id,
            "condition_ids": [fields.Command.create({"field_id": self.amount.id, "operator": ">", "value": "10000"})],
        })
        approve.next_id = send
        send.next_id = confirm
        flow._start_node().next_id = condition

        small = self.make_order(price=100)
        self.assertEqual(flow._start(small).state, "approved", "small: no approval")
        self.assertEqual(small.state, "draft")

        order = self.make_order()
        run = flow._start(order)
        self.assertEqual(run.current_step_id.user_ids, self.manager)
        run.with_user(self.manager).current_step_id._decide("approve")
        self.assertEqual(run.state, "approved")
        self.assertEqual(order.state, "sale")
        self.assertTrue(order.message_ids.filtered(lambda m: m.partner_ids == self.customer))

    def test_customer_without_email_stops_the_step(self):
        flow = self.env["angels.flow"].create({
            "name": "Send", "model_id": self.env["ir.model"]._get("sale.order").id, "trigger": "manual",
        })
        send = self.env["angels.flow.node"].create({"flow_id": flow.id, "name": "Send", "node_type": "action",
                                                    "action_ref": "preset:sale_send"})
        flow._start_node().next_id = send
        self.customer.email = False
        order = self.make_order()
        with self.assertRaisesRegex(UserError, "Send could not finish: The customer Big Customer has no email"):
            flow._start(order)
        self.assertEqual(order.state, "draft")

    def test_example_flow(self):
        example = self.env.ref("angels_flow_sale.example_flow_big_quotation")
        self.assertFalse(example.active)
        example.action_activate()
        self.make_order(price=500)
        self.assertFalse(example.run_ids, "small quotation")
        order = self.make_order()
        run = example.run_ids
        self.assertEqual(run.res_id, order.id)
        self.assertIn(self.manager, run.current_step_id.user_ids)
        self.assertEqual(run.current_step_id.node_id.escalate_user_id, self.env.ref("base.user_admin"))
