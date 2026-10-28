import { registry } from "@web/core/registry";

const EMOJI = '[data-task="emoji"]';
const SEARCH = '[data-task="embed"]';

// Every model and runtime file came from this Odoo, none from a CDN or the Hub.
function checkNoExternalRequest() {
    const external = performance
        .getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((url) => !url.startsWith(location.origin) && !url.startsWith("data:") && !url.startsWith("blob:"));
    if (external.length) {
        throw new Error(`Requests left Odoo: ${external.join(", ")}`);
    }
}

// Runs the real models served by Odoo, with internet downloads off.
registry.category("web_tour.tours").add("angels_runonweb_lab_tour", {
    steps: () => [
        { trigger: `${EMOJI} [data-role="badge"].o-row-badge-ok` },
        { trigger: `${SEARCH} [data-role="badge"].o-row-badge-ok` },
        { trigger: '[data-fact="remote"]' },
        // Text to emoji (text2emoji-tiny)
        { trigger: `${EMOJI} [data-act="run"]:enabled`, run: "click" },
        { trigger: `${EMOJI} [data-metric="device"]:contains(wasm)`, timeout: 60000 },
        {
            trigger: `${EMOJI} [data-role="emojis"]`,
            run() {
                const text = this.anchor.textContent.trim();
                if (!text || text === "∅" || /[a-z]/i.test(text)) {
                    throw new Error(`The model gave no emojis: "${text}"`);
                }
            },
        },
        // Semantic search (all-MiniLM-L6-v2): "unpaid bill" must rank a payment text first.
        { trigger: `${SEARCH} [data-act="run"]:enabled`, run: "click" },
        { trigger: `${SEARCH} [data-metric="device"]:contains(wasm)`, timeout: 60000 },
        {
            trigger: `${SEARCH} [data-role="ranking"] li:first-child`,
            run() {
                const top = this.anchor.querySelector(".o-row-ranked").textContent;
                const score = Number(this.anchor.querySelector('[data-role="score"]').textContent);
                if (!/invoice|paid/i.test(top) || !(score > 0.3)) {
                    throw new Error(`Unexpected best match for "unpaid bill": "${top}" (${score})`);
                }
                const last = this.anchor.parentElement.lastElementChild.querySelector(".o-row-ranked").textContent;
                if (/invoice|paid/i.test(last)) {
                    throw new Error(`A payment text ranked last: "${last}"`);
                }
                checkNoExternalRequest();
            },
        },
        { trigger: '[data-act="test-all"]', run: "click" },
        { trigger: 'li.o-row-summary-ok[data-summary="emoji"]', timeout: 60000 },
        { trigger: 'li.o-row-summary-ok[data-summary="embed"]', timeout: 60000 },
    ],
});
