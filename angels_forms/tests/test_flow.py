import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestFormFlow(FormCase):

    def test_small_trip_needs_the_manager_only(self):
        submission = self.fill()
        self.assertEqual(submission.state, "pending")
        self.assertTrue(submission.name.startswith("REQ/"))
        self.assertEqual(submission.title, "Madrid")
        self.assertEqual(submission.step_ids.mapped("name"), ["Manager Approval"])
        self.assertEqual(submission.current_step_id.user_ids, self.boss)
        self.assertTrue(submission.with_user(self.boss).is_my_turn)
        self.assertEqual(submission.activity_ids.user_id, self.boss)
        self.decide(submission, self.boss)
        self.assertEqual(submission.state, "approved")
        self.assertFalse(submission.activity_ids)

    def test_big_trip_with_hotel_goes_to_finance_and_desk(self):
        submission = self.fill(budget=3500, hotel=True, nights=3)
        manager, finance, desk = submission.step_ids.sorted("sequence")
        self.assertEqual((manager.state, finance.state, desk.state), ("pending", "waiting", "waiting"))
        self.assertEqual(desk.step_type, "notify_done")
        with self.assertRaises(AccessError):
            self.decide(submission, self.finance)
        self.decide(submission, self.boss, comment="Fine by me")
        self.assertEqual((manager.state, finance.state), ("approved", "pending"))
        self.decide(submission, self.finance)
        self.assertEqual(submission.state, "approved")
        self.assertEqual(desk.state, "notified")
        self.assertIn(self.desk.partner_id, submission.message_partner_ids)

    def test_international_trip_needs_passport(self):
        with self.assertRaisesRegex(UserError, "Passport Number"):
            self.fill(type="International")
        submission = self.fill(type="International", passport="X123")
        self.assertEqual(submission.state, "pending")

    def test_required_hidden_question_is_not_asked(self):
        submission = self.fill(hotel=False)
        self.assertEqual(submission.state, "pending", "hotel nights are hidden, so not required")
        with self.assertRaisesRegex(UserError, "Hotel Nights"):
            self.fill(hotel=True)

    def test_reject_needs_reason_and_skips_the_rest(self):
        submission = self.fill(budget=5000, hotel=True, nights=1)
        with self.assertRaises(UserError):
            self.decide(submission, self.boss, "reject")
        self.decide(submission, self.boss, "reject", comment="Too expensive")
        self.assertEqual(submission.state, "rejected")
        self.assertEqual(submission.step_ids.mapped("state"), ["rejected", "skipped", "skipped"])
        self.assertEqual(submission.step_ids[0].comment, "Too expensive")

    def test_draft_then_edit_then_send(self):
        submission = self.fill(submit=False, destination="Lima")
        self.assertEqual((submission.state, submission.name), ("draft", "/"))
        self.assertFalse(submission.step_ids)
        data = self.travel.with_user(self.requester).get_fill_data(self.travel.id, submission.id)
        self.assertEqual(data["values"][str(self.f["destination"].id)], "Lima")
        self.env["angels.form.submission"].with_user(self.requester).save_from_filler(
            self.travel.id, submission.id, self.answers(destination="Quito"), True,
        )
        self.assertEqual((submission.state, submission.title), ("pending", "Quito"))
        with self.assertRaises(UserError):
            self.env["angels.form.submission"].with_user(self.requester).save_from_filler(
                self.travel.id, submission.id, self.answers(), False,
            )

    def test_self_approval_blocked(self):
        submission = self.fill(manager=self.requester.id)
        with self.assertRaises(UserError):
            self.decide(submission, self.requester)
        self.travel.allow_self_approval = True
        self.decide(submission, self.requester)
        self.assertEqual(submission.state, "approved")

    def test_all_rule_needs_everyone(self):
        rule = self.env.ref("angels_forms.travel_rule_manager")
        rule.write({"assign_type": "users", "user_ids": [(6, 0, (self.boss | self.desk).ids)],
                    "approval_rule": "all"})
        submission = self.fill()
        self.decide(submission, self.boss)
        self.assertEqual(submission.current_step_id.state, "pending")
        self.assertFalse(submission.with_user(self.boss).is_my_turn)
        self.decide(submission, self.desk)
        self.assertEqual(submission.state, "approved")

    def test_no_approval_rule_means_approved_at_once(self):
        self.travel.rule_ids.unlink()
        submission = self.fill()
        self.assertEqual(submission.state, "approved")

    def test_cancel(self):
        submission = self.fill()
        with self.assertRaises(AccessError):
            submission.with_user(self.boss).action_cancel()
        submission.with_user(self.requester).action_cancel()
        self.assertEqual(submission.state, "cancelled")
        self.assertFalse(submission.activity_ids)
        self.assertEqual(submission.step_ids.state, "skipped")

    def test_files_are_attached_to_the_request(self):
        data = base64.b64encode(b"ticket").decode()
        submission = self.fill(submit=False, files=[{"name": "ticket.txt", "data": data}])
        answer = submission.answer_ids.filtered(lambda a: a.field_id == self.f["files"])
        self.assertEqual(answer.attachment_ids.name, "ticket.txt")
        self.assertEqual((answer.attachment_ids.res_model, answer.attachment_ids.res_id),
                         (submission._name, submission.id))
        other = self.env["ir.attachment"].create({"name": "secret", "raw": b"x"})
        Submission = self.env["angels.form.submission"].with_user(self.requester)
        Submission.save_from_filler(self.travel.id, submission.id, self.answers(files=[
            {"id": answer.attachment_ids.id}, {"id": other.id},
        ]), False)
        self.assertEqual(answer.attachment_ids.name, "ticket.txt", "foreign files are ignored")

    def test_zero_is_an_answer(self):
        submission = self.fill(budget=0)
        self.assertEqual(submission.state, "pending")
        budget = submission.answer_ids.filtered(lambda a: a.field_id == self.f["budget"])
        self.assertEqual(budget.display_value, "0")

    def test_uploads_to_hidden_questions_are_dropped(self):
        self.f["files"].condition_ids = [(0, 0, {
            "source_field_id": self.f["hotel"].id, "operator": "=", "value": "1",
        })]
        data = base64.b64encode(b"ticket").decode()
        submission = self.fill(submit=False, hotel=False, files=[{"name": "ticket.txt", "data": data}])
        self.assertFalse(self.env["ir.attachment"].search([
            ("res_model", "=", submission._name), ("res_id", "=", submission.id),
        ]))

    def test_answers_summary(self):
        submission = self.fill(budget=1234.5, hotel=False)
        html = str(submission.answers_html)
        self.assertIn("Madrid", html)
        self.assertIn("1234.5", html)
        self.assertNotIn("Hotel Nights", html)
        self.assertNotIn("Passport", html)
