import { Component, onWillStart, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { EditorPanel } from "./editor_panel";
import { EditorStore } from "./editor_store";
import { EditorViewer } from "./editor_viewer";

export class SignEditorAction extends Component {
    static template = "easy_sign.EditorAction";
    static components = { EditorPanel, EditorViewer };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.resModel = this.props.action.params?.res_model || "sign.request";
        this.resId = this.props.action.context?.active_id;
        this.store = new EditorStore(this.orm, this.resModel, this.resId);
        onWillStart(async () => {
            await loadPDFJSAssets();
            if (this.resId) {
                await this.store.load();
            }
        });
        onWillUnmount(() => this.store.flushAll());
    }

    get breadcrumbs() {
        return (this.env.config?.breadcrumbs || []).slice(0, -1);
    }
    get data() {
        return this.store.state.data;
    }
}

registry.category("actions").add("easy_sign_editor", SignEditorAction);
