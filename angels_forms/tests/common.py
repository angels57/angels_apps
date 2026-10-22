from odoo.tests import TransactionCase, new_test_user


class FormCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.requester = new_test_user(cls.env, "frm_requester", groups="base.group_user")
        cls.boss = new_test_user(cls.env, "frm_boss", groups="base.group_user")
        cls.outsider = new_test_user(cls.env, "frm_out", groups="base.group_user")
        cls.finance = new_test_user(
            cls.env, "frm_finance", groups="base.group_user,angels_forms.group_form_manager",
        )
        cls.desk = new_test_user(cls.env, "frm_desk", groups="base.group_user")
        cls.travel = cls.env.ref("angels_forms.form_travel")
        cls.travel.rule_ids.filtered(lambda r: r.rule_type == "notify_done").user_ids = cls.desk
        finance_rule = cls.env.ref("angels_forms.travel_rule_finance")
        finance_rule.write({"assign_type": "users", "user_ids": [(6, 0, cls.finance.ids)]})
        cls.f = {
            name: cls.env.ref(f"angels_forms.travel_{name}")
            for name in ("destination", "type", "passport", "departure", "return", "reason",
                         "manager", "budget", "hotel", "nights", "hotel_notes", "files")
        }

    def answers(self, **overrides):
        values = {
            "destination": "Madrid",
            "type": "National",
            "departure": "2026-11-02",
            "return": "2026-11-04",
            "reason": "Customer visit",
            "manager": self.boss.id,
            "budget": 800,
            "hotel": False,
        }
        values.update(overrides)
        return {str(self.f[key].id): value for key, value in values.items()}

    def fill(self, user=None, submit=True, **overrides):
        Submission = self.env["angels.form.submission"].with_user(user or self.requester)
        submission_id = Submission.save_from_filler(self.travel.id, False, self.answers(**overrides), submit)
        return Submission.browse(submission_id)

    def decide(self, submission, user, decision="approve", comment=False):
        wizard = self.env["angels.form.decision.wizard"].with_user(user).create({
            "submission_id": submission.id, "decision": decision, "comment": comment,
        })
        return wizard.action_confirm()
