from odoo import _, models
from odoo.exceptions import UserError


class AngelsFlow(models.Model):
    _inherit = "angels.flow"

    def _flow_action_choices(self):
        choices = super()._flow_action_choices()
        if self.model_name == "sale.order":
            choices.insert(0, {
                "key": "preset:sale_send",
                "label": _("Send by email to the customer"),
                "group": _("Sales"),
            })
        return choices


class AngelsFlowNode(models.Model):
    _inherit = "angels.flow.node"

    def _flow_run_preset(self, key, record):
        if key != "sale_send":
            return super()._flow_run_preset(key, record)
        template = record._find_mail_template()
        if not template:
            raise UserError(_("Sales has no email template for this order."))
        if not record.partner_id.email:
            raise UserError(_("The customer %(customer)s has no email.", customer=record.partner_id.display_name))
        record._portal_ensure_token()
        record.message_post_with_source(
            template,
            email_layout_xmlid="mail.mail_notification_layout_with_responsible_signature",
            subtype_xmlid="mail.mt_comment",
        )
        if record.state == "draft":
            record.action_quotation_sent()
        return True
