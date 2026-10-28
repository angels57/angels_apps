import { esc } from "./lab_utils";

const lines = (value) => value.split("\n").map((line) => line.trim()).filter(Boolean);

// Lab panel of each task: its fields (with the example that "Test all" uses), how to check
// and convert them into the task input, and how to show the result. Labels and messages are
// keys of lab_labels.js. A new task adds an entry here and one in core/loader.js.
// The models only understand English: the examples are not translated.
export const LAB_TASKS = {
    emoji: {
        title: "Text to emoji",
        fields: [{ name: "input", label: "Text (in English)", rows: 2, example: "I love pizza and my dog" }],
        validate: (values) => (values.input.trim() ? null : "Enter a text first."),
        toInput: (values) => values.input,
        renderResult: (result) =>
            `<div class="o-row-emojis" data-role="emojis">${esc(result.text) || "∅"}</div>`,
        summary: (result) => result.text,
    },
    embed: {
        title: "Semantic search",
        fields: [
            { name: "query", label: "Search for (in English)", rows: 1, example: "unpaid bill" },
            {
                name: "texts",
                label: "Texts to rank, one per line",
                rows: 5,
                example: [
                    "The invoice from March is still waiting for payment",
                    "Our dog loves running in the park",
                    "Reminder: the customer has not paid yet",
                    "The team meeting moves to Friday",
                    "Pizza night with friends on Saturday",
                ].join("\n"),
            },
        ],
        validate: (values) => {
            if (!values.query.trim()) {
                return "Enter what to search for.";
            }
            return lines(values.texts).length < 2 ? "Enter at least two texts, one per line." : null;
        },
        toInput: (values) => ({ query: values.query.trim(), texts: lines(values.texts) }),
        renderResult: (result) =>
            `<ol class="o-row-ranking" data-role="ranking">${result.ranking
                .map(({ text, score }) => {
                    const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
                    return `<li><span class="o-row-score" data-role="score">${score.toFixed(2)}</span>
                        <span class="o-row-bar"><span style="width: ${pct}%"></span></span>
                        <span class="o-row-ranked">${esc(text)}</span></li>`;
                })
                .join("")}</ol>`,
        summary: (result) => `${result.ranking[0]?.text ?? ""} (${result.ranking[0]?.score.toFixed(2) ?? "-"})`,
    },
};

// Example values of every field of a task.
export function examples(ui) {
    return Object.fromEntries(ui.fields.map((field) => [field.name, field.example]));
}
