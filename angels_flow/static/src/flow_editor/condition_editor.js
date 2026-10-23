import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { RecordSelector } from "@web/core/record_selectors/record_selector";
import { useProps, useState } from "../common/owl_compat";

/** "Only if" rows of a question or a rule. Mutates ``props.item`` in place. */
export class ConditionEditor extends Component {
    static template = "angels_flow.ConditionEditor";
    static components = { RecordSelector };

    setup() {
        // item, sources, labels, operatorsByType, onChange, emptyText, lead, summary
        this.props = useProps();
        this.item = useState(this.props.item);
    }

    get sources() {
        return this.props.sources;
    }
    source(condition) {
        return this.sources.find((f) => f.id === condition.source_id);
    }
    operators(condition) {
        const source = this.source(condition);
        return source ? this.props.operatorsByType[source.type] : [];
    }
    /** Choices of a selection come as plain texts (form questions) or as {value, label}. */
    optionValue(option) {
        return typeof option === "object" ? option.value : option;
    }
    optionLabel(option) {
        return typeof option === "object" ? option.label : option;
    }
    firstOption(source) {
        return source.options?.length ? this.optionValue(source.options[0]) : "";
    }
    needsValue(condition) {
        return !["set", "not_set"].includes(condition.operator);
    }
    changed() {
        this.props.onChange();
    }

    add() {
        const source = this.sources.at(-1);
        if (!source) {
            return;
        }
        this.item.conditions.push({
            source_id: source.id,
            operator: this.props.operatorsByType[source.type][0],
            value: source.type === "boolean" ? "1" : ["selection", "multi"].includes(source.type) ? this.firstOption(source) : "",
        });
        this.changed();
    }
    remove(index) {
        this.item.conditions.splice(index, 1);
        this.changed();
    }
    setSource(condition, ev) {
        const source = this.sources.find((f) => String(f.id) === ev.target.value);
        condition.source_id = source.id;
        const allowed = this.props.operatorsByType[source.type];
        if (!allowed.includes(condition.operator)) {
            condition.operator = allowed[0];
        }
        condition.value = source.type === "boolean" ? "1" : ["selection", "multi"].includes(source.type) ? this.firstOption(source) : "";
        this.changed();
    }
    setOperator(condition, ev) {
        condition.operator = ev.target.value;
        this.changed();
    }
    recordValue(condition) {
        return parseInt(condition.value, 10) || false;
    }
    setValue(condition, value) {
        condition.value = value === false || value === undefined ? "" : String(value);
        this.changed();
    }
    get match() {
        return this.item.match === "any" ? "any" : "all";
    }
    get glue() {
        return this.match === "any" ? _t("or") : _t("and");
    }
    setMatch(match) {
        this.item.match = match;
        this.changed();
    }
}
