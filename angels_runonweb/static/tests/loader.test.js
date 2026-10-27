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
});
