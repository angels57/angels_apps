import { _t } from "@web/core/l10n/translation";
import { nodeTypes } from "@angels_flow/flow_editor/node_types";

// The Create Record step of the flow designer; its settings are in RecordEditor.
nodeTypes.add("record", {
    icon: "fa-cubes",
    sequence: 50,
    palette: true,
    defaults: { record_model: false, record_model_name: "", attach_files: true, mappings: [] },
    summary: (node) =>
        node.record_model ? _t("Creates a %s", node.record_model_name || node.record_model) : _t("No record type yet"),
    pills: (node) =>
        node.record_model
            ? [
                  { icon: "fa-cube", text: node.record_model_name || node.record_model },
                  { icon: "fa-list", text: _t("%s fields", node.mappings.length), muted: true },
              ]
            : [],
});
