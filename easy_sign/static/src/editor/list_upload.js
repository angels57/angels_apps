import { useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

export function readPdfFiles(fileList) {
    return Promise.all([...fileList].map((file) => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ name: file.name, data: reader.result.split(",")[1] });
        reader.onerror = reject;
        reader.readAsDataURL(file);
    })));
}

/** "New" becomes "Upload PDF": the PDF opens straight in the editor. */
export class EasySignListController extends ListController {
    static template = "easy_sign.ListView";

    setup() {
        super.setup();
        this.easySignOrm = useService("orm");
        this.uploadInput = useRef("esUpload");
    }

    onClickUpload() {
        this.uploadInput.el.click();
    }

    async onUploadChange(ev) {
        const files = await readPdfFiles(ev.target.files);
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        const action = await this.easySignOrm.call(this.props.resModel, "create_from_upload", [files]);
        await this.actionService.doAction(action);
    }

    async openRecord(record, options) {
        const toEditor = this.props.resModel === "sign.template" || record.data.state === "draft";
        if (!toEditor) {
            return super.openRecord(record, options);
        }
        const action = await this.easySignOrm.call(this.props.resModel, "action_open_editor", [[record.resId]]);
        return this.actionService.doAction(action);
    }
}

registry.category("views").add("easy_sign_list", { ...listView, Controller: EasySignListController });
