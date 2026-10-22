from odoo.tests import TransactionCase, new_test_user


class ApprovalCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        user_group = "base.group_user,angels_approvals.group_approval_user"
        cls.requester = new_test_user(cls.env, "apr_requester", groups=user_group)
        cls.approver_a = new_test_user(cls.env, "apr_a", groups=user_group)
        cls.approver_b = new_test_user(cls.env, "apr_b", groups=user_group)
        cls.outsider = new_test_user(cls.env, "apr_out", groups=user_group)
        cls.manager = new_test_user(
            cls.env, "apr_manager",
            groups="base.group_user,angels_approvals.group_approval_manager",
        )
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.partner = cls.env["res.partner"].create({"name": "Big Customer", "is_company": True})
        cls.flow = cls.env["angels.approval.flow"].create({
            "name": "Customer approval",
            "model_id": cls.partner_model.id,
            "domain": "[('is_company', '=', True)]",
            "company_id": False,
            "step_ids": [
                (0, 0, {"name": "Sales", "user_ids": [(6, 0, cls.approver_a.ids)]}),
                (0, 0, {"name": "Finance", "user_ids": [(6, 0, cls.approver_b.ids)]}),
            ],
        })

    def submit(self, record=None, flow=None, user=None, note="Please"):
        record = record or self.partner
        user = user or self.requester
        Wizard = self.env["angels.approval.request.wizard"].with_user(user).with_context(
            active_model=record._name, active_ids=record.ids,
        )
        wizard = Wizard.create({"flow_id": (flow or self.flow).id, "note": note})
        action = wizard.action_submit()
        return self.env["angels.approval.request"].browse(action["res_id"])

    def decide(self, request, user, decision="approve", comment=False):
        wizard = self.env["angels.approval.decision.wizard"].with_user(user).create({
            "request_id": request.id, "decision": decision, "comment": comment,
        })
        return wizard.action_confirm()
