import { registry } from "@web/core/registry";

const EMOJI = '[data-task="emoji"]';

// Runs the real text2emoji-tiny model served by Odoo, with internet downloads off.
registry.category("web_tour.tours").add("angels_runonweb_lab_tour", {
    steps: () => [
        { trigger: `${EMOJI} [data-role="badge"].o-row-badge-ok` },
        { trigger: '[data-fact="remote"]' },
        { trigger: `${EMOJI} [data-act="run"]:enabled`, run: "click" },
        { trigger: `${EMOJI} [data-metric="device"]:contains(wasm)`, timeout: 60000 },
        {
            trigger: `${EMOJI} [data-role="emojis"]`,
            run() {
                const text = this.anchor.textContent.trim();
                if (!text || text === "∅" || /[a-z]/i.test(text)) {
                    throw new Error(`The model gave no emojis: "${text}"`);
                }
                // Every model and runtime file came from this Odoo, none from a CDN or the Hub.
                const external = performance
                    .getEntriesByType("resource")
                    .map((entry) => entry.name)
                    .filter((url) => !url.startsWith(location.origin) && !url.startsWith("data:") && !url.startsWith("blob:"));
                if (external.length) {
                    throw new Error(`Requests left Odoo: ${external.join(", ")}`);
                }
            },
        },
        { trigger: '[data-act="test-all"]', run: "click" },
        { trigger: 'li.o-row-summary-ok[data-summary="emoji"]', timeout: 60000 },
    ],
});
