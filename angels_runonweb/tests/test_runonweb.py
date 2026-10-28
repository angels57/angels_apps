from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..utils import catalog, storage
from .common import StorageMixin


@tagged("post_install", "-at_install")
class TestRunOnWeb(StorageMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.user = new_test_user(cls.env, login="row_user", groups="base.group_user")
        cls.portal = new_test_user(cls.env, login="row_portal", groups="base.group_portal")
        cls.runonweb = cls.env["angels.runonweb"]

    def download_all(self, task="emoji"):
        with patch.object(storage, "download", side_effect=self.fake_download):
            return self.runonweb.with_user(self.admin).download_task(task)

    def test_config_for_internal_users(self):
        config = self.runonweb.with_user(self.user).get_config()
        self.assertEqual(config["device"], "auto")
        self.assertEqual(config["modelPath"], "/angels_runonweb/models/")
        self.assertEqual(config["wasmPaths"], {
            "mjs": "/angels_runonweb/runtime/ort-wasm-simd-threaded.asyncify.mjs",
            "wasm": "/angels_runonweb/runtime/ort-wasm-simd-threaded.asyncify.wasm",
        })
        emoji = config["tasks"]["emoji"]
        self.assertEqual((emoji["model"], emoji["license"]), ("midudev/text2emoji-tiny", "MIT"))
        self.assertEqual(emoji["size"], catalog.task_size("emoji"))
        # Nothing on the server and internet downloads off by default: the task cannot run.
        self.assertEqual((emoji["local"], emoji["available"]), (False, False))

    def test_wasm_paths_are_served_by_the_runtime_route(self):
        config = self.runonweb.get_config()
        for url in config["wasmPaths"].values():
            self.assertIsNotNone(catalog.find("runtime", url.removeprefix("/angels_runonweb/runtime/")))

    def test_internet_downloads_make_the_task_available(self):
        self.set_allow_remote(True)
        emoji = self.runonweb.with_user(self.user).get_config()["tasks"]["emoji"]
        self.assertEqual((emoji["local"], emoji["available"]), (False, True))

    def test_invalid_device_falls_back_to_auto(self):
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param("angels_runonweb.device", "wasm")
        self.assertEqual(self.runonweb.get_config()["device"], "wasm")
        icp.set_param("angels_runonweb.device", "quantum")
        self.assertEqual(self.runonweb.get_config()["device"], "auto")

    def test_portal_users_get_no_config(self):
        with self.assertRaises(AccessError):
            self.runonweb.with_user(self.portal).get_config()

    def test_only_administrators_manage_models(self):
        model = self.runonweb.with_user(self.user)
        for method, args in [("get_status", ()), ("download_task", ("emoji",)), ("remove_task", ("emoji",))]:
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(model, method)(*args)

    def test_download_then_remove(self):
        status = self.download_all()
        self.assertTrue(status["runtime"]["local"])
        self.assertTrue(status["tasks"]["emoji"]["local"])
        self.assertTrue(self.runonweb.with_user(self.user).get_config()["tasks"]["emoji"]["available"])
        self.assertEqual(status["storage"], self.storage_dir)

        status = self.runonweb.with_user(self.admin).remove_task("emoji")
        self.assertFalse(status["tasks"]["emoji"]["local"])
        # The runtime is shared by every task and stays.
        self.assertTrue(status["runtime"]["local"])
        self.assertFalse(any(storage.is_present(e) for e in catalog.task_files("emoji")))

    def test_semantic_search_task(self):
        embed = self.runonweb.with_user(self.user).get_config()["tasks"]["embed"]
        self.assertEqual((embed["model"], embed["license"]), ("Xenova/all-MiniLM-L6-v2", "Apache-2.0"))
        self.assertEqual(embed["size"], catalog.task_size("embed"))
        self.assertFalse(embed["available"])

    def test_tasks_are_downloaded_and_removed_separately(self):
        status = self.download_all("embed")
        self.assertTrue(status["tasks"]["embed"]["local"])
        self.assertFalse(status["tasks"]["emoji"]["local"])
        # Both WebGPU (fp16) and WASM (q8) weights, so any browser can run it.
        for name in ("onnx/model_fp16.onnx", "onnx/model_quantized.onnx"):
            self.assertTrue(storage.is_present(catalog.find("models", f"Xenova/all-MiniLM-L6-v2/{name}")))

        self.download_all("emoji")
        status = self.runonweb.with_user(self.admin).remove_task("emoji")
        self.assertEqual((status["tasks"]["emoji"]["local"], status["tasks"]["embed"]["local"]), (False, True))

    def test_download_skips_files_already_there(self):
        self.download_all()
        with patch.object(storage, "download") as download:
            self.runonweb.with_user(self.admin).download_task("emoji")
        download.assert_not_called()

    def test_download_fetches_only_missing_files(self):
        self.download_all()
        storage.remove(self.emoji_entry("tokenizer.json"))
        with patch.object(storage, "download", side_effect=self.fake_download) as download:
            self.runonweb.with_user(self.admin).download_task("emoji")
        self.assertEqual([call.args[0].path for call in download.call_args_list], ["midudev/text2emoji-tiny/tokenizer.json"])

    def test_download_errors_are_user_errors(self):
        with patch.object(storage, "download", side_effect=storage.DownloadError("offline")):
            with self.assertRaisesRegex(UserError, "offline"):
                self.runonweb.with_user(self.admin).download_task("emoji")

    def test_unknown_task(self):
        for method in ("download_task", "remove_task"):
            with self.subTest(method=method), self.assertRaises(UserError):
                getattr(self.runonweb.with_user(self.admin), method)("../../etc")

    def test_spanish_translations(self):
        self.env["res.lang"]._activate_lang("es_ES")
        self.env["ir.module.module"]._load_module_terms(["angels_runonweb"], ["es_ES"], overwrite=True)
        menu = self.env.ref("angels_runonweb.menu_runonweb_lab")
        self.assertEqual(menu.name, "RunOnWeb Lab")
        self.assertEqual(menu.with_context(lang="es_ES").name, "Laboratorio RunOnWeb")
        field = self.env["res.config.settings"]._fields["runonweb_allow_remote"]
        self.assertEqual(field._description_string(self.env(context={"lang": "es_ES"})),
                         "Descargar de internet los modelos que falten")
        with self.assertRaisesRegex(UserError, "Tarea de RunOnWeb desconocida"):
            self.runonweb.with_user(self.admin).with_context(lang="es_ES").download_task("nope")

    def test_settings_store_the_parameters(self):
        settings = self.env["res.config.settings"].create({
            "runonweb_allow_remote": True,
            "runonweb_device": "webgpu",
        })
        settings.execute()
        status = self.runonweb.with_user(self.admin).get_status()
        self.assertEqual((status["allowRemote"], status["device"]), (True, "webgpu"))
