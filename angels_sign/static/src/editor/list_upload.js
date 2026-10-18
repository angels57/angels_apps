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

/** Open the browser's file picker for PDFs and resolve with the chosen files, read as base64. */
export function pickPdfFiles() {
    return new Promise((resolve) => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = "application/pdf";
        input.multiple = true;
        input.addEventListener("change", () => resolve(readPdfFiles(input.files)));
        input.click();
    });
}

/** "New" becomes "Upload PDF": the PDF opens straight in the editor. */
export class AngelsSignListController extends ListController {
    static template = "angels_sign.ListView";

    setup() {
        super.setup();
        this.angelsSignOrm = useService("orm");
    }

    async onClickUpload() {
        const files = await pickPdfFiles();
        if (!files.length) {
            return;
        }
        const action = await this.angelsSignOrm.call(this.props.resModel, "create_from_upload", [files]);
        await this.actionService.doAction(action);
    }

    async openRecord(record, options) {
        const toEditor = this.props.resModel === "sign.template" || record.data.state === "draft";
        if (!toEditor) {
            return super.openRecord(record, options);
        }
        const action = await this.angelsSignOrm.call(this.props.resModel, "action_open_editor", [[record.resId]]);
        return this.actionService.doAction(action);
    }
}

registry.category("views").add("angels_sign_list", {
    ...listView,
    Controller: AngelsSignListController,
    buttonTemplate: "angels_sign.ListView.Buttons",
});
