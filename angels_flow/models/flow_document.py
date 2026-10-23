from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

STATES = [
    ("draft", "Draft"),
    ("pending", "In Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("cancelled", "Cancelled"),
]


class AngelsFlowDocumentMixin(models.AbstractModel):
    """A document that walks a flow, from its Start to an End.

    The model that inherits it declares ``step_ids``, the steps it reached
    (a model inheriting ``angels.flow.step.mixin``), and says what the flow
    reads (``_flow_values``), who asked (``_flow_requester``) and which
    activity its people get (``_flow_activity_type``).
    """

    _name = "angels.flow.document.mixin"
    _description = "Flow Document"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    state = fields.Selection(STATES, required=True, default="draft", readonly=True, tracking=True, index=True)
    date_done = fields.Datetime(string="Decided On", readonly=True)

    # ------------------------------------------------------------------
    # What the flow needs from the document
    # ------------------------------------------------------------------

    def _flow_values(self):
        """Values the steps read (conditions, recipients...)."""
        self.ensure_one()
        return {}

    def _flow_requester(self):
        self.ensure_one()
        return self.env["res.users"]

    def _flow_allow_self_approval(self):
        self.ensure_one()
        return False

    def _flow_activity_type(self):
        return self.env.ref("mail.mail_activity_data_todo")

    def _flow_run_node(self, node, values):
        """Run a step kind added by another module; return the next step."""
        raise UserError(_("The step %(step)s cannot run.", step=node.name))

    # ------------------------------------------------------------------
    # Walking the flow
    # ------------------------------------------------------------------

    def _flow_run(self, node):
        """Walk the flow from ``node`` until a step waits for people, or the end.

        A missing link ends the flow: the document is approved.
        """
        self.ensure_one()
        values = self._flow_values()
        Step = self.env[self.step_ids._name].sudo()
        seen = set()
        while node:
            if node.id in seen:
                raise UserError(_("The flow goes round in a circle at %(step)s.", step=node.name))
            seen.add(node.id)
            kind = node.node_type
            if kind == "start":
                node = node.next_id
            elif kind == "condition":
                node = node.yes_id if node._flow_condition_met(values) else node.no_id
            elif kind == "end":
                return self._flow_finish(node.end_state or "approved")
            elif kind == "back":
                return self._flow_send_back(node)
            elif kind in ("approve", "task", "notify"):
                recipients = node._get_recipients(values)
                if not recipients:
                    if kind == "notify":
                        node = node.next_id
                        continue
                    raise UserError(_("Nobody can do the step %(step)s.", step=node.name))
                step = Step.create({
                    Step._flow_document: self.id,
                    "node_id": node.id,
                    "sequence": len(self.step_ids) + 1,
                    "name": node.name,
                    "step_type": kind,
                    "approval_rule": node.approval_rule or "any",
                    "user_ids": [fields.Command.set(recipients.ids)],
                })
                if kind == "notify":
                    step._notify(Markup("<p>%s</p>") % _(
                        "%(step)s: request %(request)s from %(user)s.",
                        step=node.name, request=self.display_name, user=self._flow_requester().name,
                    ))
                    node = node.next_id
                    continue
                step._activate()
                return True
            else:
                node = self._flow_run_node(node, values)
        return self._flow_finish("approved")

    def _flow_send_back(self, node):
        """Reopen the document so the requester corrects it and sends it again."""
        self.ensure_one()
        requester = self._flow_requester()
        self.sudo().write({"state": "draft"})
        self.step_ids._flow_close_activities()
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % _("%(step)s: the request goes back to %(user)s to be corrected.",
                                         step=node.name, user=requester.name),
            partner_ids=requester.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        self.sudo().activity_schedule(
            activity_type_id=self._flow_activity_type().id,
            summary=_("Correct %(request)s", request=self.display_name),
            user_id=requester.id,
        )
        return True

    def _flow_close_requester_activities(self):
        activity_type = self._flow_activity_type()
        requester = self._flow_requester()
        self.sudo().activity_ids.filtered(
            lambda a: a.activity_type_id == activity_type and a.user_id == requester
        ).unlink()

    def _flow_finish(self, state):
        self.ensure_one()
        self.sudo().write({"state": state, "date_done": fields.Datetime.now()})
        self.step_ids._flow_close_activities()
        if state == "approved":
            body = _("The request %(request)s was approved.", request=self.display_name)
        else:
            body = _("The request %(request)s was rejected.", request=self.display_name)
        self.sudo().message_post(
            body=Markup("<p>%s</p>") % body,
            partner_ids=self._flow_requester().partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )
        return True

    def _flow_cancel(self):
        """Stop the flow: pending steps are skipped and their activities closed."""
        for document in self:
            document.sudo().write({"state": "cancelled", "date_done": fields.Datetime.now()})
            document.step_ids.filtered(lambda s: s.state == "pending").sudo().write({"state": "skipped"})
            document.step_ids._flow_close_activities()
