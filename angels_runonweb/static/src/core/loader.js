// Plain JS (no OWL): the backend service and public pages share it.
// The runonweb build is not part of any asset bundle: each task entry is imported by URL the
// first time it is needed, and its model downloads only then.
export const LIB_URL = "/angels_runonweb/static/lib/runonweb";

// Task name -> build entry, class and the method that runs it.
export const TASKS = {
    emoji: { entry: "emoji.js", className: "Emojifier", method: "emojify" },
};

export function configureRuntime(env, config) {
    const wasm = env?.backends?.onnx?.wasm;
    if (wasm) {
        // Transformers.js defaults to jsDelivr: Odoo serves (or redirects to) the same files.
        wasm.wasmPaths = { ...config.wasmPaths };
        if (!globalThis.crossOriginIsolated) {
            wasm.numThreads = 1;
        }
    }
    if (env) {
        env.useBrowserCache = true;
    }
}

export async function detectWebGPU() {
    try {
        return Boolean(await globalThis.navigator?.gpu?.requestAdapter());
    } catch {
        return false;
    }
}

export class RunOnWebLoader {
    constructor({ importModule = (url) => import(url), baseUrl = LIB_URL } = {}) {
        this.importModule = importModule;
        this.baseUrl = baseUrl;
        this.instances = new Map();
        this.listeners = new Set();
    }

    onProgress(listener) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    emit(task, info) {
        for (const listener of this.listeners) {
            listener({ task, ...info });
        }
    }

    // Resolves to a loaded task instance; the same options reuse the same instance.
    load(task, config, options = {}) {
        const spec = TASKS[task];
        if (!spec) {
            return Promise.reject(new Error(`Unknown RunOnWeb task: ${task}`));
        }
        const state = config?.tasks?.[task];
        if (!state?.available) {
            return Promise.reject(new Error(`The "${task}" model is not available on this server.`));
        }
        const key = `${task}:${JSON.stringify(options)}`;
        if (!this.instances.has(key)) {
            const promise = this.create(task, spec, state, config, options);
            // A failed load (network, memory) can be retried later.
            promise.catch(() => this.instances.delete(key));
            this.instances.set(key, promise);
        }
        return this.instances.get(key);
    }

    async create(task, spec, state, config, options) {
        const lib = await this.importModule(`${this.baseUrl}/${spec.entry}`);
        configureRuntime(lib.env, config);
        const instance = new lib[spec.className]({
            model: state.model,
            modelPath: config.modelPath,
            device: config.device,
            ...options,
            onProgress: (info) => this.emit(task, info),
        });
        await instance.load();
        return instance;
    }

    async run(task, config, input, options = {}) {
        const instance = await this.load(task, config, options);
        return instance[TASKS[task].method](input);
    }

    async dispose() {
        const pending = [...this.instances.values()];
        this.instances.clear();
        for (const promise of pending) {
            const instance = await promise.catch(() => null);
            await instance?.dispose?.();
        }
    }
}
