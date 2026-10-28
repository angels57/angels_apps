import { describe, expect, test } from "@odoo/hoot";

import { configureRuntime, RunOnWebLoader } from "@angels_runonweb/core/loader";

const CONFIG = {
    device: "auto",
    modelPath: "/angels_runonweb/models/",
    wasmPaths: { mjs: "/angels_runonweb/runtime/a.mjs", wasm: "/angels_runonweb/runtime/a.wasm" },
    tasks: { emoji: { model: "midudev/text2emoji-tiny", available: true } },
};

// A fake build entry that records what the loader did with it.
function fakeLib({ failLoads = 0 } = {}) {
    const lib = {
        imports: [],
        created: [],
        disposed: 0,
        env: { backends: { onnx: { wasm: {} } } },
    };
    lib.Emojifier = class {
        constructor(options) {
            this.options = options;
            this.device = "wasm";
            lib.created.push(this);
        }
        async load() {
            this.options.onProgress({ status: "progress", progress: 50 });
            if (failLoads > 0) {
                failLoads--;
                throw new Error("out of memory");
            }
        }
        async emojify(text) {
            return { text: `[${text}]`, emojis: [text] };
        }
        dispose() {
            lib.disposed++;
        }
    };
    const importModule = async (url) => {
        lib.imports.push(url);
        return lib;
    };
    return { lib, loader: new RunOnWebLoader({ importModule }) };
}

describe("RunOnWeb loader", () => {
    test("imports the task entry and creates it with the server paths", async () => {
        const { lib, loader } = fakeLib();
        const instance = await loader.load("emoji", CONFIG);
        expect(lib.imports).toEqual(["/angels_runonweb/static/lib/runonweb/emoji.js"]);
        expect(instance.options.model).toBe("midudev/text2emoji-tiny");
        expect(instance.options.modelPath).toBe("/angels_runonweb/models/");
        expect(instance.options.device).toBe("auto");
        expect(lib.env.backends.onnx.wasm.wasmPaths).toEqual(CONFIG.wasmPaths);
        expect(lib.env.useBrowserCache).toBe(true);
    });

    test("loads a task once and reuses it", async () => {
        const { lib, loader } = fakeLib();
        const [a, b] = await Promise.all([loader.load("emoji", CONFIG), loader.load("emoji", CONFIG)]);
        expect(a).toBe(b);
        expect(lib.created.length).toBe(1);
        const other = await loader.load("emoji", CONFIG, { maxEmojis: 3 });
        expect(other).not.toBe(a);
        expect(other.options.maxEmojis).toBe(3);
    });

    test("runs the task method", async () => {
        const { loader } = fakeLib();
        expect(await loader.run("emoji", CONFIG, "pizza")).toEqual({ text: "[pizza]", emojis: ["pizza"] });
    });

    test("rejects unknown and unavailable tasks", async () => {
        const { lib, loader } = fakeLib();
        await expect(loader.load("telepathy", CONFIG)).rejects.toThrow(/Unknown RunOnWeb task/);
        const off = { ...CONFIG, tasks: { emoji: { ...CONFIG.tasks.emoji, available: false } } };
        await expect(loader.load("emoji", off)).rejects.toThrow(/not available/);
        expect(lib.imports).toEqual([]);
    });

    test("a failed load can be retried", async () => {
        const { lib, loader } = fakeLib({ failLoads: 1 });
        await expect(loader.load("emoji", CONFIG)).rejects.toThrow("out of memory");
        const instance = await loader.load("emoji", CONFIG);
        expect(instance.device).toBe("wasm");
        expect(lib.created.length).toBe(2);
    });

    test("forwards progress with the task name", async () => {
        const { loader } = fakeLib();
        const seen = [];
        const stop = loader.onProgress((info) => seen.push(info));
        await loader.load("emoji", CONFIG);
        stop();
        await loader.load("emoji", CONFIG, { maxEmojis: 1 });
        expect(seen).toEqual([{ task: "emoji", status: "progress", progress: 50 }]);
    });

    test("dispose frees every loaded task", async () => {
        const { lib, loader } = fakeLib();
        await loader.load("emoji", CONFIG);
        await loader.load("emoji", CONFIG, { maxEmojis: 2 });
        await loader.dispose();
        expect(lib.disposed).toBe(2);
        await loader.load("emoji", CONFIG);
        expect(lib.created.length).toBe(3);
    });

    test("configureRuntime ignores a build without ONNX settings", () => {
        expect(() => configureRuntime(undefined, CONFIG)).not.toThrow();
        const env = { backends: {} };
        configureRuntime(env, CONFIG);
        expect(env.useBrowserCache).toBe(true);
    });

    test("configureRuntime points the Hub at Odoo with an absolute URL", () => {
        const env = { remoteHost: "https://huggingface.co/", remotePathTemplate: "{model}/resolve/{revision}/" };
        configureRuntime(env, CONFIG);
        expect(env.remoteHost).toBe(`${location.origin}/angels_runonweb/models/`);
        expect(env.remotePathTemplate).toBe("{model}/");
    });

    test("semantic search ranks the texts by similarity to the query", async () => {
        const created = [];
        const lib = {
            env: {},
            // Vectors are 1-D: the similarity is the product of the two numbers.
            cosineSimilarity: (a, b) => a[0] * b[0],
            TextEmbedder: class {
                constructor(options) {
                    this.options = options;
                    created.push(this);
                }
                async load() {}
                async embed(texts) {
                    this.texts = texts;
                    const value = { "unpaid bill": 1, "invoice overdue": 0.9, dog: 0.1, meeting: 0.3 };
                    return { embeddings: texts.map((t) => new Float32Array([value[t]])), dimensions: 1 };
                }
            },
        };
        const loader = new RunOnWebLoader({ importModule: async () => lib });
        const config = { ...CONFIG, tasks: { embed: { model: "Xenova/all-MiniLM-L6-v2", available: true } } };
        const result = await loader.run("embed", config, { query: "unpaid bill", texts: ["dog", "invoice overdue", "meeting"] });
        // One call embeds the query and the texts together.
        expect(created[0].texts).toEqual(["unpaid bill", "dog", "invoice overdue", "meeting"]);
        expect(created[0].options.model).toBe("Xenova/all-MiniLM-L6-v2");
        expect(result.dimensions).toBe(1);
        expect(result.ranking.map((r) => r.text)).toEqual(["invoice overdue", "meeting", "dog"]);
        expect(result.ranking[0].score).toBeCloseTo(0.9, { digits: 5 });
    });
});
