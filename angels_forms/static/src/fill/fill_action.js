import { Component, onWillStart } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { isSet, visibleFieldIds } from "../common/conditions";
import { FormRenderer } from "../common/form_renderer";
import { useProps, useState } from "../common/owl_compat";

/** Fill a form: new request, or edit a draft (context: form_id, submission_id). */
export class FormFillAction extends Component {
    static template = "angels_forms.FillAction";
    static components = { FormRenderer };

    setup() {
        this.props = useProps();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        this.formId = context.form_id;
        this.submissionId = context.submission_id || false;
        this.state = useState({ data: null, saving: false });
        this.values = useState({});
        this.errors = useState({});
        onWillStart(async () => {
            const data = await this.orm.call("angels.form", "get_fill_data", [this.formId, this.submissionId]);
            Object.assign(this.values, data.values);
            this.state.data = data;
        });
    }

    get breadcrumbs() {
        return (this.env.config?.breadcrumbs || []).slice(0, -1);
    }
    get fields() {
        return this.state.data.fields;
    }

    /** Only the answers of visible questions go to the server. */
    payload() {
        const visible = visibleFieldIds(this.fields, this.values);
        return Object.fromEntries(Object.entries(this.values).filter(([key]) => visible.has(key)));
    }

    validate() {
        const visible = visibleFieldIds(this.fields, this.values);
        for (const key of Object.keys(this.errors)) {
            delete this.errors[key];
        }
        for (const field of this.fields) {
            const key = String(field.id);
            if (field.type !== "section" && field.required && visible.has(key) && !isSet(this.values[key])) {
                this.errors[key] = _t("Please answer this question.");
            }
        }
        const missing = Object.keys(this.errors);
        if (missing.length) {
            document.querySelector(`.o_af_fill [data-field-id="${missing[0]}"]`)?.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });
        }
        return !missing.length;
    }

    async save(submit) {
        if (this.state.saving || (submit && !this.validate())) {
            return;
        }
        this.state.saving = true;
        try {
            const id = await this.orm.call("angels.form.submission", "save_from_filler", [
                this.formId,
                this.submissionId,
                this.payload(),
                submit,
            ]);
            this.notification.add(submit ? _t("Your request was sent.") : _t("Draft saved."), {
                type: "success",
            });
            await this.actionService.doAction(
                {
                    type: "ir.actions.act_window",
                    res_model: "angels.form.submission",
                    res_id: id,
                    views: [[false, "form"]],
                    target: "current",
                },
                { stackPosition: "replaceCurrentAction" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    discard() {
        const previous = this.breadcrumbs.at(-1);
        if (previous) {
            previous.onSelected();
        } else {
            this.actionService.doAction("angels_forms.action_form_catalog");
        }
    }
}

registry.category("actions").add("angels_forms_fill", FormFillAction);
