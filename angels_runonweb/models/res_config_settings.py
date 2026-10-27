from odoo import fields, models

from .runonweb import PARAM_ALLOW_REMOTE, PARAM_DEVICE


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    runonweb_allow_remote = fields.Boolean(
        string="Download missing models from the internet",
        config_parameter=PARAM_ALLOW_REMOTE,
        help="When a model is not on this server, browsers download it from Hugging Face and "
             "jsDelivr. Leave it off to keep every download on this server.",
    )
    runonweb_device = fields.Selection(
        [("auto", "Automatic"), ("webgpu", "WebGPU"), ("wasm", "WASM")],
        string="Inference device",
        config_parameter=PARAM_DEVICE,
        default="auto",
        help="Automatic uses WebGPU when the browser has it and WASM otherwise.",
    )
