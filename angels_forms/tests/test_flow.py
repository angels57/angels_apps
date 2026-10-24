import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestFormFlow(FormCase):

    def test_small_trip_goes_to_the_manager_then_the_travel_desk(self):
        submission = self.fill()
        self.assertEqual(submission.state, "pending")
        self.assertTrue(submission.name.startswith("REQ/"))
        self.assertEqual(submission.title, "Madrid")
        self.assertEqual(submission.current_step_id.name, "Manager Approval")
        self.assertEqual(submission.current_step_id.user_ids, self.boss)
        self.assertTrue(submission.with_user(self.boss).is_my_turn)
        self.assertEqual(submission.activity_ids.user_id, self.boss)
        self.decide(submission, self.boss)
        booking = submission.current_step_id
        self.assertEqual((booking.name, booking.step_type), ("Book the Trip", "task"))
        self.assertEqual(submission.activity_ids.user_id, self.desk)
        with self.assertRaisesRegex(UserError, "Booking Reference"):
            self.step(submission, self.desk)
        self.step(submission, self.desk, booking_ref="IB-1234")
        self.assertEqual(submission.state, "approved")
        self.assertEqual(submission.step_ids.mapped("state"), ["approved", "done"])
        self.assertFalse(submission.activity_ids)

    def test_big_trip_needs_finance_and_its_questions(self):
        submission = self.fill(budget=3500)
        self.decide(submission, self.boss)
        self.assertEqual(submission.current_step_id.name, "Finance Approval")
        # Approving opens the fill screen because Finance has questions to answer.
        action = submission.with_user(self.finance).action_approve()
        self.assertEqual(action["tag"], "angels_forms_fill")
        with self.assertRaisesRegex(UserError, "Cost Center"):
            self.decide(submission, self.finance)
        self.step(submission, self.finance, done=False, cost_center="CC-42")
        self.assertEqual(submission.current_step_id.name, "Finance Approval", "saved, not approved yet")
        html = str(submission.answers_html)
        self.assertIn("CC-42", html)
        self.assertIn("o_af_stage", html)
        self.assertNotIn("Booking Reference", html, "the booking step is not reached yet")
        self.step(submission, self.finance, cost_center="CC-42", approved_amount=3000, comment="OK")
        self.assertEqual(submission.current_step_id.name, "Book the Trip")
        self.assertIn("Booking Reference", str(submission.answers_html))

    def test_requester_cannot_answer_the_questions_of_a_step(self):
        submission = self.fill(cost_center="hack")
        self.assertFalse(submission.answer_ids.filtered(lambda a: a.field_id == self.f["cost_center"]))
        with self.assertRaises(UserError):
            self.step(submission, self.finance, cost_center="CC-1")
        with self.assertRaises(UserError):
            self.step(submission, self.outsider, cost_center="CC-1")

    def test_step_saves_only_its_own_questions(self):
        submission = self.fill(budget=3500)
        self.decide(submission, self.boss)
        self.step(submission, self.finance, done=False, cost_center="CC-9", destination="Paris")
        self.assertEqual(submission.title, "Madrid")

    def test_manager_rejection_goes_back_to_the_requester(self):
        submission = self.fill()
        name = submission.name
        self.decide(submission, self.boss, "reject", comment="Wrong dates")
        self.assertEqual(submission.state, "draft")
        self.assertTrue(submission.with_user(self.requester).can_edit)
        self.assertEqual(submission.activity_ids.user_id, self.requester)
        Submission = self.env["angels.form.submission"].with_user(self.requester)
        Submission.save_from_filler(self.travel.id, submission.id, self.answers(departure="2026-11-03"), True)
        self.assertEqual((submission.state, submission.name), ("pending", name))
        self.assertEqual(submission.step_ids.mapped("state"), ["rejected", "pending"])
        self.assertEqual(submission.activity_ids.user_id, self.boss)

    def test_finance_rejection_rejects_the_request(self):
        submission = self.fill(budget=5000)
        self.decide(submission, self.boss)
        with self.assertRaises(UserError):
            self.decide(submission, self.finance, "reject")
        self.decide(submission, self.finance, "reject", comment="Too expensive")
        self.assertEqual(submission.state, "rejected")
        self.assertEqual(submission.step_ids.mapped("state"), ["approved", "rejected"])

    def test_tasks_cannot_be_rejected(self):
        submission = self.fill()
        self.decide(submission, self.boss)
        with self.assertRaises(UserError):
            submission.current_step_id.with_user(self.desk)._decide("reject", "no")

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

    def test_notification_end_and_missing_links(self):
        Node = self.env["angels.form.node"]
        notify = Node.create({
            "form_id": self.travel.id, "name": "Inform HR", "node_type": "notify",
            "assign_type": "users", "user_ids": [(6, 0, self.outsider.ids)],
            "next_id": self.n["manager"].id,
        })
        self.n["start"].next_id = notify
        reject_end = Node.create({
            "form_id": self.travel.id, "name": "Refused", "node_type": "end", "end_state": "rejected",
        })
        self.n["budget"].yes_id = reject_end
        submission = self.fill(budget=9000)
        self.assertEqual(submission.step_ids[0].state, "notified")
        self.assertIn(self.outsider.partner_id, submission.message_partner_ids)
        self.decide(submission, self.boss)
        self.assertEqual(submission.state, "rejected", "the yes branch ends rejected")
        # A step without a next step ends the flow approved.
        self.n["manager"].next_id = False
        other = self.fill()
        self.decide(other, self.boss)
        self.assertEqual(other.state, "approved")

    def test_loops_are_reported(self):
        self.n["budget"].no_id = self.n["budget"]
        submission = self.fill()
        with self.assertRaisesRegex(UserError, "circle"):
            self.decide(submission, self.boss)

    def test_draft_then_edit_then_send(self):
        submission = self.fill(submit=False, destination="Lima")
        self.assertEqual((submission.state, submission.name), ("draft", "/"))
        self.assertFalse(submission.step_ids)
        data = self.travel.with_user(self.requester).get_fill_data(self.travel.id, submission.id)
        self.assertEqual(data["values"][str(self.f["destination"].id)], "Lima")
        self.assertNotIn(self.f["cost_center"].id, [f["id"] for f in data["fields"]])
        self.env["angels.form.submission"].with_user(self.requester).save_from_filler(
            self.travel.id, submission.id, self.answers(destination="Quito"), True,
        )
        self.assertEqual((submission.state, submission.title), ("pending", "Quito"))
        with self.assertRaises(UserError):
            self.env["angels.form.submission"].with_user(self.requester).save_from_filler(
                self.travel.id, submission.id, self.answers(), False,
            )

    def test_step_fill_data(self):
        submission = self.fill(budget=3500)
        self.decide(submission, self.boss)
        data = self.travel.with_user(self.finance).get_fill_data(self.travel.id, submission.id)
        editable = {f["id"] for f in data["fields"] if f["editable"]}
        shown = {f["id"] for f in data["fields"]}
        self.assertIn(self.f["cost_center"].id, editable)
        self.assertNotIn(self.f["destination"].id, editable)
        self.assertIn(self.f["destination"].id, shown)
        self.assertNotIn(self.f["booking_ref"].id, shown)
        self.assertEqual(data["submission"]["step"]["name"], "Finance Approval")
        with self.assertRaises(UserError):
            self.travel.with_user(self.boss).get_fill_data(self.travel.id, submission.id)

    def test_self_approval_blocked(self):
        submission = self.fill(manager=self.requester.id)
        with self.assertRaises(UserError):
            self.decide(submission, self.requester)
        self.travel.allow_self_approval = True
        self.decide(submission, self.requester)
        self.assertEqual(submission.current_step_id.name, "Book the Trip")

    def test_all_rule_needs_everyone(self):
        self.n["manager"].write({"assign_type": "users", "user_ids": [(6, 0, (self.boss | self.outsider).ids)],
                                 "approval_rule": "all"})
        submission = self.fill()
        self.decide(submission, self.boss)
        self.assertEqual(submission.current_step_id.name, "Manager Approval")
        self.assertFalse(submission.with_user(self.boss).is_my_turn)
        self.decide(submission, self.outsider)
        self.assertEqual(submission.current_step_id.name, "Book the Trip")

    def test_empty_flow_approves_at_once(self):
        self.n["start"].next_id = False
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

    def test_trail_of_a_request(self):
        submission = self.fill()
        data = submission.with_user(self.requester).get_flow_trail()
        visited = [entry["node"] for entry in data["trail"]]
        self.assertEqual(visited[0], self.n["start"].id)
        self.assertEqual(data["current"], visited[-1])
        self.assertEqual(submission.current_step_id.node_id.id, data["current"])
        self.decide(submission, self.boss)
        self.assertGreater(len(submission.get_flow_trail()["trail"]), len(visited))

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

    def test_multiple_choice_and_number_affixes(self):
        extras = self.env["angels.form.field"].create({
            "form_id": self.travel.id, "sequence": 115, "name": "Extras", "field_type": "multi",
            "options": "Breakfast\nParking\nLate checkout",
        })
        self.f["budget"].write({"prefix": "€"})
        values = self.answers(budget=900)
        values[str(extras.id)] = ["Parking", "Breakfast"]
        Submission = self.env["angels.form.submission"].with_user(self.requester)
        submission = Submission.browse(Submission.save_from_filler(self.travel.id, False, values, True))
        answer = submission.answer_ids.filtered(lambda a: a.field_id == extras)
        self.assertEqual(answer._get_value(), ["Parking", "Breakfast"])
        self.assertEqual(answer.display_value, "Parking, Breakfast")
        self.assertEqual(submission._answers_to_client()[str(extras.id)], ["Parking", "Breakfast"])
        budget = submission.answer_ids.filtered(lambda a: a.field_id == self.f["budget"])
        self.assertEqual(budget.display_value, "€ 900")
        Condition = self.env["angels.form.condition"]
        condition = Condition.new({"source_field_id": extras.id, "operator": "contains", "value": "parking"})
        self.assertTrue(condition._matches({extras.id: ["Parking", "Breakfast"]}))
        self.assertFalse(condition._matches({extras.id: ["Breakfast"]}))
        self.assertFalse(condition._matches({extras.id: False}))

    def test_answers_summary(self):
        submission = self.fill(budget=1234.5, hotel=False)
        html = str(submission.answers_html)
        self.assertIn("Madrid", html)
        self.assertIn("1234.5", html)
        self.assertNotIn("Hotel Nights", html)
        self.assertNotIn("Passport", html)
        self.assertNotIn("Cost Center", html)
