from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import FormCase


@tagged("post_install", "-at_install")
class TestFormSecurity(FormCase):

    def test_visibility(self):
        submission = self.fill(budget=3000)
        Submission = self.env["angels.form.submission"]
        self.assertIn(submission, Submission.with_user(self.requester).search([]))
        self.assertIn(submission, Submission.with_user(self.boss).search([]))
        self.assertNotIn(submission, Submission.with_user(self.outsider).search([]))
        # Finance only sees it once it is their turn (they are also a manager, so use a plain user).
        self.env.ref("angels_forms.travel_rule_finance").user_ids = self.desk
        later = self.fill(budget=3000)
        self.assertNotIn(later, Submission.with_user(self.desk).search([]))
        self.decide(later, self.boss)
        self.assertIn(later, Submission.with_user(self.desk).search([]))
        with self.assertRaises(AccessError):
            submission.with_user(self.outsider).read(["title"])
        with self.assertRaises(AccessError):
            submission.answer_ids.with_user(self.outsider).read(["display_value"])

    def test_users_cannot_forge_state(self):
        submission = self.fill()
        with self.assertRaises(AccessError):
            submission.with_user(self.requester).write({"state": "approved"})
        with self.assertRaises(AccessError):
            submission.answer_ids[:1].with_user(self.requester).write({"value_char": "Paris"})

    def test_only_drafts_can_be_deleted(self):
        draft = self.fill(submit=False)
        sent = self.fill()
        with self.assertRaises(AccessError):
            draft.with_user(self.outsider).unlink()
        with self.assertRaises(UserError):
            sent.with_user(self.requester).unlink()
        draft.with_user(self.requester).unlink()
        self.assertFalse(draft.exists())

    def test_form_access(self):
        self.travel.group_ids = self.env.ref("base.group_system")
        with self.assertRaises(AccessError):
            self.fill()
        with self.assertRaises(AccessError):
            self.travel.with_user(self.requester).action_fill()
        self.travel.group_ids = False
        self.travel.published = False
        with self.assertRaises(AccessError):
            self.fill()

    def test_other_users_draft_is_private(self):
        draft = self.fill(submit=False)
        with self.assertRaises(AccessError):
            self.travel.with_user(self.outsider).get_fill_data(self.travel.id, draft.id)
        with self.assertRaises(AccessError):
            self.env["angels.form.submission"].with_user(self.outsider).save_from_filler(
                self.travel.id, draft.id, self.answers(), True,
            )

    def test_configuration_needs_manager(self):
        with self.assertRaises(AccessError):
            self.env["angels.form"].with_user(self.requester).create({"name": "Mine"})
        with self.assertRaises(AccessError):
            self.f["budget"].with_user(self.requester).write({"required": False})
