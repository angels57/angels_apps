// Builds ../static/lib/runonweb from the pinned runonweb package.
//   cd modules/angels_runonweb/tools && npm ci && npm run build
// runonweb ships TypeScript sources: esbuild turns each entry of entries/ into a browser ES
// module, with the shared Transformers.js and ONNX Runtime code in chunks/.
import { build } from "esbuild";
import { copyFile, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const outdir = join(here, "..", "static", "lib", "runonweb");
const entries = (await readdir(join(here, "entries"))).filter((name) => name.endsWith(".js"));

await rm(outdir, { recursive: true, force: true });
await build({
    entryPoints: entries.map((name) => join(here, "entries", name)),
    bundle: true,
    format: "esm",
    platform: "browser",
    splitting: true,
    minify: true,
    legalComments: "none",
    outdir,
    entryNames: "[name]",
    chunkNames: "chunks/[name]-[hash]",
    logLevel: "info",
});

// Licenses of the bundled code travel with it. runonweb and onnxruntime-web publish no
// LICENSE file in their npm packages: their MIT notice is written from the holder below.
const MIT = (holder) => `MIT License

Copyright (c) ${holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
`;
const licenses = join(outdir, "licenses");
await mkdir(licenses, { recursive: true });
for (const [pkg, file, holder] of [
    ["runonweb", "runonweb.LICENSE", "Miguel Ángel Durán (midudev)"],
    ["@huggingface/transformers", "transformers.LICENSE"],
    // The copy Transformers.js bundles, not the one runonweb lists.
    ["@huggingface/transformers/node_modules/onnxruntime-web", "onnxruntime-web.LICENSE", "Microsoft Corporation"],
]) {
    const source = join(here, "node_modules", pkg, "LICENSE");
    const target = join(licenses, file);
    await copyFile(source, target).catch(() => writeFile(target, MIT(holder)));
}
