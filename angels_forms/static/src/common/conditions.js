/**
 * Same rules as angels.form.condition / angels.form._visible_values on the
 * server: the browser hides questions as you type, the server checks again.
 * Values are keyed by the field id as a string.
 */

export const OPERATORS_BY_TYPE = {
    char: ["=", "!=", "contains", "set", "not_set"],
    text: ["contains", "set", "not_set"],
    number: ["=", "!=", ">", ">=", "<", "<=", "set", "not_set"],
    date: ["=", "!=", ">", ">=", "<", "<=", "set", "not_set"],
    datetime: ["set", "not_set"],
    boolean: ["=", "!="],
    selection: ["=", "!=", "set", "not_set"],
    multi: ["contains", "set", "not_set"],
    user: ["=", "!=", "set", "not_set"],
    partner: ["=", "!=", "set", "not_set"],
    file: ["set", "not_set"],
};
const TRUE_WORDS = ["1", "true", "yes"];

export function isSet(value) {
    return !(
        value === false ||
        value === null ||
        value === undefined ||
        value === "" ||
        (Array.isArray(value) && !value.length)
    );
}

function normalize(type, raw) {
    if (!isSet(raw) && type !== "boolean") {
        return false;
    }
    switch (type) {
        case "char":
        case "text":
        case "selection":
            return String(raw).trim().toLowerCase() || false;
        case "number": {
            const number = Number(raw);
            return Number.isNaN(number) ? false : number;
        }
        case "date":
            return String(raw).slice(0, 10);
        case "boolean":
            return typeof raw === "string" ? TRUE_WORDS.includes(raw.trim().toLowerCase()) : Boolean(raw);
        case "user":
        case "partner":
            return parseInt(raw, 10) || false;
        default:
            return raw;
    }
}

export function conditionMatches(condition, source, values) {
    const actualRaw = values[String(source.id)];
    const { operator } = condition;
    if (operator === "set") {
        return isSet(actualRaw);
    }
    if (operator === "not_set") {
        return !isSet(actualRaw);
    }
    if (source.type === "boolean") {
        const expected = TRUE_WORDS.includes((condition.value || "").trim().toLowerCase());
        return (Boolean(actualRaw) === expected) === (operator === "=");
    }
    if (source.type === "multi") {
        // "contains": the choice is one of the ticked ones.
        const ticked = (actualRaw || []).map((choice) => String(choice).toLowerCase());
        return operator === "contains" && ticked.includes((condition.value || "").trim().toLowerCase());
    }
    const actual = normalize(source.type, actualRaw);
    const expected = normalize(source.type, condition.value);
    if (!isSet(actual) || !isSet(expected)) {
        return operator === "!=" && isSet(actual) !== isSet(expected);
    }
    switch (operator) {
        case "=":
            return actual === expected;
        case "!=":
            return actual !== expected;
        case "contains":
            return String(actual).includes(String(expected));
        case ">":
            return actual > expected;
        case ">=":
            return actual >= expected;
        case "<":
            return actual < expected;
        case "<=":
            return actual <= expected;
    }
    return false;
}

export function conditionsMet(item, fieldsById, values) {
    const conditions = (item.conditions || []).filter((c) => fieldsById[String(c.source_id)]);
    if (!conditions.length) {
        return true;
    }
    const results = conditions.map((c) => conditionMatches(c, fieldsById[String(c.source_id)], values));
    return item.match === "any" ? results.some(Boolean) : results.every(Boolean);
}

/** Ids (as strings) of the questions shown for ``values``, in order. */
export function visibleFieldIds(fields, values) {
    const fieldsById = Object.fromEntries(fields.map((f) => [String(f.id), f]));
    const effective = {};
    const visible = new Set();
    let sectionShown = true;
    for (const field of fields) {
        const key = String(field.id);
        let shown = conditionsMet(field, fieldsById, effective);
        if (field.type === "section") {
            sectionShown = shown;
        } else {
            shown = shown && sectionShown;
            effective[key] = shown ? values[key] : false;
        }
        if (shown) {
            visible.add(key);
        }
    }
    return visible;
}
