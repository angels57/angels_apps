// Plain JS (no OWL): the backend service and public pages share it.
// The runonweb build is not part of any asset bundle: each task entry is imported by URL the
// first time it is needed, and its model downloads only then.
export const LIB_URL = "/angels_runonweb/static/lib/runonweb";

// Ranks `texts` by meaning against `query`, best match first.
async function semanticSearch(instance, { query, texts }, lib) {
    const { embeddings, dimensions } = await instance.embed([query, ...texts]);
    const [target, ...vectors] = embeddings;
    const ranking = texts
        .map((text, index) => ({ text, score: lib.cosineSimilarity(target, vectors[index]) }))
        .sort((a, b) => b.score - a.score);
    return { ranking, dimensions };
}

// Task name -> build entry, class and how to run it: the method called with the input, or
// `run(instance, input, lib)` when the task needs more than one call.
export const TASKS = {
    emoji: { entry: "emoji.js", className: "Emojifier", method: "emojify" },
    embed: { entry: "embed.js", className: "TextEmbedder", run: semanticSearch },
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
        // Tasks that take no `modelPath` ask the Hub: point the Hub at Odoo, with the same
        // <model>/<file> layout. Absolute, so the browser cache accepts the responses.
        env.remoteHost = new URL(config.modelPath, globalThis.location?.href).href;
        env.remotePathTemplate = "{model}/";
    }
}

// Cache Storage buckets of the models: Transformers.js and runonweb's own ones.
export const MODEL_CACHE_PREFIXES = ["transformers-cache", "runonweb-"];
const OWN_FILE = /^\/angels_runonweb\/(models|runtime)\//;

// Deletes the cached files of older catalog versions: their URLs are never asked again, so
// they would only take space. Returns how many entries went.
export async function pruneStaleCache(config, cacheStorage = globalThis.caches) {
    if (!cacheStorage) {
        return 0;
    }
    const base = globalThis.location?.href;
    const current = [config.modelPath, config.wasmPaths.wasm.replace(/[^/]*$/, "")].map(
        (path) => new URL(path, base).pathname,
    );
    let removed = 0;
    for (const name of await cacheStorage.keys()) {
        if (!MODEL_CACHE_PREFIXES.some((prefix) => name.startsWith(prefix))) {
            continue;
        }
        const cache = await cacheStorage.open(name);
        for (const request of await cache.keys()) {
            const { pathname } = new URL(request.url, base);
            if (OWN_FILE.test(pathname) && !current.some((path) => pathname.startsWith(path))) {
                await cache.delete(request);
                removed++;
            }
        }
    }
    return removed;
}

export async function detectWebGPU() {
    try {
        return Boolean(await globalThis.navigator?.gpu?.requestAdapter());
    } catch {
        return false;
    }
}

export class RunOnWebLoader {
    constructor({ importModule = (url) => import(url), baseUrl = LIB_URL, cacheStorage = globalThis.caches } = {}) {
        this.importModule = importModule;
        this.baseUrl = baseUrl;
        this.cacheStorage = cacheStorage;
        this.pruning = null;
        this.instances = new Map();
        this.libs = new Map();
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
        // Once per page, before any model goes into the cache. A cache that cannot be read
        // (private window) must not stop the task.
        this.pruning ??= pruneStaleCache(config, this.cacheStorage).catch(() => 0);
        await this.pruning;
        const lib = await this.importModule(`${this.baseUrl}/${spec.entry}`);
        this.libs.set(task, lib);
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
        const spec = TASKS[task];
        return spec.run ? spec.run(instance, input, this.libs.get(task)) : instance[spec.method](input);
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
