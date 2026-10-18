from odoo import fields, models


class SignRole(models.Model):
    _name = "sign.role"
    _description = "Signature Role"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(default=1)
    default_partner_id = fields.Many2one(
        "res.partner", string="Fixed Signer",
        help="Always use this contact for the role (for example, the company representative).",
    )
    auth_method = fields.Selection(
        selection=lambda self: self.env["sign.request.item"]._fields["auth_method"].selection,
        string="Verification", default="none", required=True,
    )
    can_delegate = fields.Boolean(string="Can Be Replaced")


class SignTag(models.Model):
    _name = "sign.tag"
    _description = "Signature Tag"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    color = fields.Integer()

    _name_unique = models.Constraint("UNIQUE (name)", "This tag already exists.")
