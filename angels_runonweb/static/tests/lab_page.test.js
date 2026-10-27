import { describe, expect, getFixture, test } from "@odoo/hoot";
import { patchTranslations } from "@web/../tests/web_test_helpers";

import { LabPage } from "@angels_runonweb/lab/lab_page";

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function status({ local = false, allowRemote = false } = {}) {
    return {
        allowRemote,
        device: "auto",
        storage: "/var/lib/odoo/angels_runonweb",
        runtime: { version: "1.31.0", size: 26914834, local },
        tasks: {
            emoji: {
                name: "Text to emoji", model: "midudev/text2emoji-tiny", license: "MIT",
                licenseUrl: "https://huggingface.co/midudev/text2emoji-tiny",
                size: 4375353, local, available: local || allowRemote,
            },
        },
    };
}

// A fake angels_runonweb service.
function fakeRunonweb({ fail = null } = {}) {
    const service = {
        loads: [],
        runs: [],
        disposed: 0,
        configRefreshed: 0,
        listener: null,
        async load(task) {
            service.loads.push(task);
            service.listener?.({ task, status: "progress", progress: 40 });
            if (fail) {
                throw new Error(fail);
            }
            return { device: "wasm" };
        },
        async run(task, input) {
            service.runs.push([task, input]);
            return { text: "🍕❤️🐶", emojis: ["🍕", "❤️", "🐶"] };
        },
        async getConfig(refresh) {
            service.configRefreshed += refresh ? 1 : 0;
        },
        onProgress(listener) {
            service.listener = listener;
            return () => (service.listener = null);
        },
        async dispose() {
            service.disposed++;
        },
    };
    return service;
}

async function mount({ backend = {}, runonweb = fakeRunonweb(), probe = {} } = {}) {
    patchTranslations();
    const calls = [];
    const root = document.createElement("div");
    getFixture().appendChild(root);
    const answers = { get_status: status(), ...backend };
    const page = new LabPage(root, {
        call: async (method, ...args) => {
            calls.push([method, ...args]);
            const answer = answers[method];
            if (answer instanceof Error) {
                throw answer;
            }
            return typeof answer === "function" ? answer(...args) : answer;
        },
        runonweb,
        probe: { webgpu: async () => false, isolated: () => false, cacheSize: async () => 0, clearCache: async () => {}, ...probe },
    });
    await page.start();
    return { page, root, calls, runonweb };
}

const q = (root, selector) => root.querySelector(selector);

async function click(root, selector) {
    q(root, selector).click();
    await settle();
    await settle();
}

describe("RunOnWeb lab", () => {
    test("shows the browser and server diagnostics", async () => {
        const { root } = await mount({ probe: { webgpu: async () => true, cacheSize: async () => 5 * 1024 * 1024 } });
        expect(q(root, '[data-fact="webgpu"]').textContent).toBe("Available");
        expect(q(root, '[data-fact="threads"]').textContent).toInclude("One");
        expect(q(root, '[data-fact="cache"]').textContent).toBe("5.0 MB");
        expect(q(root, '[data-fact="remote"]').textContent).toBe("Off");
        expect(q(root, '[data-fact="runtime"]').textContent).toInclude("Not downloaded");
        expect(root.textContent).toInclude("/var/lib/odoo/angels_runonweb");
    });

    test("a task that cannot load is marked and cannot run", async () => {
        const { root } = await mount();
        const panel = q(root, '[data-task="emoji"]');
        expect(q(panel, '[data-role="badge"]').textContent).toBe("Not available");
        expect(q(panel, '[data-act="run"]').disabled).toBe(true);
        expect(q(panel, '[data-act="download"]')).not.toBe(null);
        expect(panel.textContent).toInclude("download it to the server");
        expect(q(panel, "[data-field=input]").value).toBe("I love pizza and my dog");
    });

    test("internet downloads make the task runnable without local files", async () => {
        const { root } = await mount({ backend: { get_status: status({ allowRemote: true }) } });
        const panel = q(root, '[data-task="emoji"]');
        expect(q(panel, '[data-role="badge"]').textContent).toBe("From the internet");
        expect(q(panel, '[data-act="run"]').disabled).toBe(false);
    });

    test("run shows the emojis, the timings and the device", async () => {
        const { root, runonweb } = await mount({ backend: { get_status: status({ local: true }) } });
        q(root, '[data-task="emoji"] [data-field=input]').value = "pizza night";
        await click(root, '[data-task="emoji"] [data-act="run"]');
        expect(runonweb.runs).toEqual([["emoji", "pizza night"]]);
        expect(q(root, '[data-role="emojis"]').textContent).toBe("🍕❤️🐶");
        expect(q(root, '[data-metric="device"]').textContent).toBe("wasm");
        expect(q(root, '[data-metric="load"]').textContent).toMatch(/^\d+ ms$/);
        expect(q(root, '[data-metric="run"]').textContent).toMatch(/^\d+ ms$/);
        expect(q(root, '[data-task="emoji"] [data-role="progress"]').hidden).toBe(false);
        expect(q(root, '[data-role="progress-text"]').textContent).toBe("Downloading 40%");
    });

    test("an empty text is refused before loading anything", async () => {
        const { root, runonweb } = await mount({ backend: { get_status: status({ local: true }) } });
        const input = q(root, '[data-task="emoji"] [data-field=input]');
        input.value = "   ";
        await click(root, '[data-task="emoji"] [data-act="run"]');
        expect(q(root, '[data-task="emoji"] [data-role="error"]').textContent).toBe("Enter a text first.");
        expect(runonweb.loads).toEqual([]);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        expect(q(root, '[data-task="emoji"] [data-role="error"]').textContent).toBe("");
        await click(root, '[data-task="emoji"] [data-act="example"]');
        expect(input.value).toBe("I love pizza and my dog");
    });

    test("a load error is shown in the panel", async () => {
        const { root } = await mount({
            backend: { get_status: status({ local: true }) },
            runonweb: fakeRunonweb({ fail: "WebAssembly out of memory" }),
        });
        await click(root, '[data-task="emoji"] [data-act="run"]');
        expect(q(root, '[data-task="emoji"] [data-role="error"]').textContent).toBe("WebAssembly out of memory");
        expect(q(root, '[data-role="emojis"]')).toBe(null);
    });

    test("download to the server refreshes the status and the config", async () => {
        const { root, calls, runonweb } = await mount({ backend: { download_task: status({ local: true }) } });
        await click(root, '[data-task="emoji"] [data-act="download"]');
        expect(calls.filter((c) => c[0] === "download_task")).toEqual([["download_task", "emoji"]]);
        expect(runonweb.configRefreshed).toBe(1);
        expect(q(root, '[data-task="emoji"] [data-role="badge"]').textContent).toBe("On the server");
        expect(q(root, '[data-task="emoji"] [data-act="remove"]')).not.toBe(null);
        expect(q(root, '[data-fact="runtime"]').textContent).toInclude("On the server");
    });

    test("a server error stays in the panel and keeps the typed text", async () => {
        const error = Object.assign(new Error("RPC_ERROR"), { data: { message: "The model could not be downloaded: offline" } });
        const { root } = await mount({ backend: { download_task: error } });
        q(root, '[data-task="emoji"] [data-field=input]').value = "my text";
        await click(root, '[data-task="emoji"] [data-act="download"]');
        expect(q(root, '[data-task="emoji"] [data-role="error"]').textContent).toInclude("offline");
        expect(q(root, '[data-task="emoji"] [data-field=input]').value).toBe("my text");
    });

    test("remove from the server", async () => {
        const { root, calls } = await mount({
            backend: { get_status: status({ local: true }), remove_task: status() },
        });
        await click(root, '[data-task="emoji"] [data-act="remove"]');
        expect(calls.some((c) => c[0] === "remove_task" && c[1] === "emoji")).toBe(true);
        expect(q(root, '[data-task="emoji"] [data-role="badge"]').textContent).toBe("Not available");
    });

    test("test all runs every available task with its example", async () => {
        const { root, runonweb } = await mount({ backend: { get_status: status({ local: true }) } });
        await click(root, '[data-act="test-all"]');
        expect(runonweb.runs).toEqual([["emoji", "I love pizza and my dog"]]);
        const row = q(root, '[data-summary="emoji"]');
        expect(row.classList.contains("o-row-summary-ok")).toBe(true);
        expect(row.textContent).toInclude("🍕❤️🐶");
    });

    test("test all reports unavailable and failing tasks", async () => {
        let { root } = await mount();
        await click(root, '[data-act="test-all"]');
        expect(q(root, '[data-summary="emoji"]').classList.contains("o-row-summary-off")).toBe(true);

        ({ root } = await mount({
            backend: { get_status: status({ local: true }) },
            runonweb: fakeRunonweb({ fail: "boom" }),
        }));
        await click(root, '[data-act="test-all"]');
        const row = q(root, '[data-summary="emoji"]');
        expect(row.classList.contains("o-row-summary-fail")).toBe(true);
        expect(row.textContent).toInclude("boom");
    });

    test("clearing the cache frees the models and empties the browser cache", async () => {
        let cleared = 0;
        let size = 3 * 1024 * 1024;
        const { root, runonweb } = await mount({
            probe: { cacheSize: async () => size, clearCache: async () => { cleared++; size = 0; } },
        });
        expect(q(root, '[data-fact="cache"]').textContent).toBe("3.0 MB");
        await click(root, '[data-act="clear-cache"]');
        expect(runonweb.disposed).toBe(1);
        expect(cleared).toBe(1);
        expect(q(root, '[data-fact="cache"]').textContent).toBe("0 MB");
        expect(q(root, '[data-role="summary"]').textContent).toInclude("empty");
    });

    test("texts are escaped", async () => {
        const evil = status({ local: true });
        evil.storage = '<img src=x onerror="window.pwned=1">';
        const { root } = await mount({ backend: { get_status: evil } });
        expect(q(root, "img")).toBe(null);
        expect(root.textContent).toInclude("<img src=x");
    });

    test("destroy stops listening to progress", async () => {
        const { page, root, runonweb } = await mount();
        page.destroy();
        expect(runonweb.listener).toBe(null);
        expect(root.innerHTML).toBe("");
    });
});
