from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import str2bool

from ..utils import catalog, storage

PARAM_ALLOW_REMOTE = "angels_runonweb.allow_remote"
PARAM_DEVICE = "angels_runonweb.device"
DEVICES = ("auto", "webgpu", "wasm")
BASE_URL = "/angels_runonweb"


class AngelsRunonweb(models.AbstractModel):
    _name = "angels.runonweb"
    _description = "RunOnWeb Browser AI Runtime"

    # ------------------------------------------------------------------ helpers

    @api.model
    def _allow_remote(self):
        return str2bool(self.env["ir.config_parameter"].sudo().get_param(PARAM_ALLOW_REMOTE, "False"))

    @api.model
    def _device(self):
        device = self.env["ir.config_parameter"].sudo().get_param(PARAM_DEVICE) or "auto"
        return device if device in DEVICES else "auto"

    @api.model
    def _check_task(self, task):
        if task not in catalog.TASKS:
            raise UserError(_("Unknown RunOnWeb task: %s", task))

    @api.model
    def _check_admin(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can manage the RunOnWeb models."))

    @api.model
    def _task_state(self, task):
        files = catalog.runtime_files() + catalog.task_files(task)
        local = all(storage.is_present(entry) for entry in files)
        spec = catalog.TASKS[task]
        return {
            "name": spec["name"],
            "model": spec["model"],
            "license": spec["license"],
            "licenseUrl": spec["license_url"],
            "size": catalog.task_size(task),
            "local": local,
            "available": local or self._allow_remote(),
        }

    # ------------------------------------------------------------------ public API

    @api.model
    def get_config(self):
        """What the browser needs to run the tasks: paths, device and which tasks can load."""
        if not self.env.user._is_internal():
            raise AccessError(_("RunOnWeb is only available to internal users."))
        runtime = f"{BASE_URL}/runtime/{catalog.version('runtime')}"
        return {
            "device": self._device(),
            "modelPath": f"{BASE_URL}/models/{catalog.version('models')}/",
            "wasmPaths": {
                "mjs": f"{runtime}/ort-wasm-simd-threaded.asyncify.mjs",
                "wasm": f"{runtime}/ort-wasm-simd-threaded.asyncify.wasm",
            },
            "tasks": {task: self._task_state(task) for task in catalog.TASKS},
        }

    @api.model
    def get_status(self):
        """Lab and settings view of the server side: where files live and what is missing."""
        self._check_admin()
        runtime = catalog.runtime_files()
        return {
            "allowRemote": self._allow_remote(),
            "device": self._device(),
            "storage": storage.root(),
            "runtime": {
                "version": catalog.ORT_VERSION,
                "size": catalog.runtime_size(),
                "local": all(storage.is_present(entry) for entry in runtime),
            },
            "tasks": {task: self._task_state(task) for task in catalog.TASKS},
        }

    @api.model
    def download_task(self, task):
        """Download the runtime and the model of `task` to the server, then report the status."""
        self._check_admin()
        self._check_task(task)
        for entry in catalog.runtime_files() + catalog.task_files(task):
            if storage.is_present(entry):
                continue
            try:
                storage.download(entry)
            except storage.DownloadError as error:
                raise UserError(_("The model could not be downloaded: %s", error)) from error
        return self.get_status()

    @api.model
    def remove_task(self, task):
        """Delete the model files of `task` from the server. The shared runtime stays."""
        self._check_admin()
        self._check_task(task)
        for entry in catalog.task_files(task):
            try:
                storage.remove(entry)
            except storage.StorageError as error:
                raise UserError(_("The model could not be removed: %s", error)) from error
        return self.get_status()
