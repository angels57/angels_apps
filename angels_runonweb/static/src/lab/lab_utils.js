import { MODEL_CACHE_PREFIXES } from "../core/loader";

const ESCAPES ={ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

export function formatBytes(bytes) {
    if (!bytes) {
        return "0 MB";
    }
    const mb = bytes / (1024 * 1024);
    return mb < 10 ? `${mb.toFixed(1)} MB` : `${Math.round(mb)} MB`;
}

export function errorMessage(error) {
    return error?.data?.message || error?.message || String(error);
}

// Model caches of this origin (Transformers.js and runonweb's own buckets).
async function modelCaches() {
    if (typeof caches === "undefined") {
        return [];
    }
    const names = await caches.keys();
    return names.filter((name) => MODEL_CACHE_PREFIXES.some((prefix) => name.startsWith(prefix)));
}

export async function modelCacheSize() {
    let total = 0;
    for (const name of await modelCaches()) {
        const cache = await caches.open(name);
        for (const request of await cache.keys()) {
            const response = await cache.match(request);
            total += Number(response?.headers.get("content-length") || 0);
        }
    }
    return total;
}

export async function clearModelCache() {
    for (const name of await modelCaches()) {
        await caches.delete(name);
    }
}
