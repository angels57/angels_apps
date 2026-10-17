import { Component, onWillStart, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { EditorPanel } from "./editor_panel";
import { EditorStore } from "./editor_store";
import { EditorTopbar } from "./editor_topbar";
import { EditorViewer } from "./editor_viewer";
import { useProps, useState } from "./owl_compat";

export class SignEditorAction extends Component {
    static template = "easy_sign.EditorAction";
    static components = { EditorPanel, EditorTopbar, EditorViewer };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        this.resModel = this.props.action.params?.res_model || "sign.request";
        this.resId = this.props.action.context?.active_id;
        this.store = new EditorStore(this.orm, this.resModel, this.resId);
        this.state = useState(this.store.state);
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
        return this.state.data;
    }

    async onSend() {
        await this.store.flushAll();
        const action = await this.orm.call(this.resModel, "action_send_from_editor", [[this.resId]]);
        await this.actionService.doAction(action);
    }
    async onSignNow() {
        await this.store.flushAll();
        const action = await this.orm.call(this.resModel, "action_sign_now", [[this.resId]]);
        await this.actionService.doAction(action);
    }
    async onEditCopy() {
        const action = await this.orm.call(this.resModel, "action_edit_copy", [[this.resId]]);
        await this.actionService.doAction(action);
    }
    onProperties() {
        this.dialog.add(FormViewDialog, {
            resModel: this.resModel,
            resId: this.resId,
            viewId: this.data.properties_view_id,
            title: _t("Properties"),
            onRecordSaved: () => this.store.load(),
        });
    }
}

registry.category("actions").add("easy_sign_editor", SignEditorAction);
