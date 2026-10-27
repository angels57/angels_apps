import { esc } from "./lab_utils";

// Lab panel of each task: its input, the example that "Test all" uses and how to show the
// result. A new task adds an entry here and one in core/loader.js.
export const LAB_TASKS = {
    emoji: {
        title: "Text to emoji",
        inputLabel: "Text (in English)",
        // The model only understands English: the example is not translated.
        example: () => "I love pizza and my dog",
        isEmpty: (value) => !value.trim(),
        renderResult: (result) =>
            `<div class="o-row-emojis" data-role="emojis">${esc(result.text) || "∅"}</div>`,
        summary: (result) => result.text,
    },
};
