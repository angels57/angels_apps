import { registry } from "@web/core/registry";

/**
 * Kinds of flow step the designer offers. Other modules add theirs:
 *
 *     registry.category("angels_flow.node_types").add("record", {
 *         icon: "fa-cubes",        // Font Awesome icon
 *         sequence: 60,            // place in the palette
 *         palette: true,           // offered in the palette (Start is not)
 *         defaults: {...},         // extra keys of a new step
 *         summary: (node) => "",   // one line under the name
 *         pills: (node) => [],     // small facts at the bottom: {icon, text, title, muted}
 *     });
 *
 * Their output ports come from the server (``_flow_ports``).
 */
export const nodeTypes = registry.category("angels_flow.node_types");

nodeTypes
    .add("start", { icon: "fa-play", sequence: 0, palette: false })
    .add("condition", { icon: "fa-code-fork", sequence: 10, palette: true })
    .add("approve", { icon: "fa-check-circle", sequence: 20, palette: true })
    .add("task", { icon: "fa-tasks", sequence: 30, palette: true })
    .add("notify", { icon: "fa-bell", sequence: 40, palette: true })
    .add("back", { icon: "fa-reply", sequence: 80, palette: true })
    .add("end", { icon: "fa-flag-checkered", sequence: 90, palette: true });

export function nodeIcon(type) {
    return nodeTypes.get(type, {}).icon || "fa-square-o";
}
