"""Every file the browser may ask Odoo for, pinned by version and SHA-256.

The routes only serve paths listed here, so nothing else under the storage folder can be
read, and the server downloads only these files, from these exact revisions. Their URLs
carry the version of the catalog (see `version`).
"""

import hashlib
from collections import namedtuple

# One file: where the browser asks for it, where it comes from, and what it must be.
CatalogFile = namedtuple("CatalogFile", "kind path remote_url sha256 size mimetype")
KINDS = ("models", "runtime")

ORT_VERSION = "1.31.0-dev.20260914-8d85527a0"
ORT_CDN = f"https://cdn.jsdelivr.net/npm/onnxruntime-web@{ORT_VERSION}/dist/"

# ONNX Runtime Web binaries of the version Transformers.js bundles (asyncify build, the one
# it picks when it runs on WASM or WebGPU).
RUNTIME = {
    "ort-wasm-simd-threaded.asyncify.mjs": (
        "0966b6105cd936744498aa60df7a22cbd47af3374dbc64a9ab561c08a71e3611", 53057, "text/javascript",
    ),
    "ort-wasm-simd-threaded.asyncify.wasm": (
        "49871f5a4409519797e127440868a6d1923339d9185907f301a5b2a1d90af082", 26861777, "application/wasm",
    ),
}

JSON = "application/json"
ONNX = "application/octet-stream"

TASKS = {
    "emoji": {
        "name": "Text to emoji",
        "model": "midudev/text2emoji-tiny",
        "revision": "cfdf562bf0514bebbabe42f8a9e6393828243510",
        "license": "MIT",
        "license_url": "https://huggingface.co/midudev/text2emoji-tiny",
        "files": {
            "config.json": ("907e8e73e6433e3ed91544b9e3e52edb654ef2a3880fcff5f8361649eca9b9d3", 762, JSON),
            "generation_config.json": ("7e8baecc3c762e100d27f50965672f9b24e7e03e49c93685074fae2f6df2d000", 146, JSON),
            "special_tokens_map.json": ("f43d87b94c590d88203672e50dfff4bbe82a310a695dfe1728ffb921825b57e9", 73, JSON),
            "tokenizer.json": ("aa05163088d960e31b8dcd3cd86b5a3bc9ac50b84fcbcc47d3ef9425b837ac95", 510921, JSON),
            "tokenizer_config.json": ("3268eb56c9ae1ed6fdf388c17a485dd0eb723a98ba393fcc1c7e0b687951363b", 253, JSON),
            "onnx/encoder_model_quantized.onnx": (
                "f2866c5d73b9878dff3d3a13b617821b7170c27c4b9454a46aafd25caabe9249", 1734642, ONNX,
            ),
            "onnx/decoder_model_merged_quantized.onnx": (
                "da45ee0e72df7e4d15a2a8ade7f394884708ca764f4c7eb86daefc42670d4429", 2128556, ONNX,
            ),
        },
    },
    "embed": {
        "name": "Semantic search",
        "model": "Xenova/all-MiniLM-L6-v2",
        "revision": "751bff37182d3f1213fa05d7196b954e230abad9",
        "license": "Apache-2.0",
        "license_url": "https://huggingface.co/Xenova/all-MiniLM-L6-v2",
        "files": {
            "config.json": ("7135149f7cffa1a573466c6e4d8423ed73b62fd2332c575bf738a0d033f70df7", 650, JSON),
            "special_tokens_map.json": ("b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3", 125, JSON),
            "tokenizer.json": ("da0e79933b9ed51798a3ae27893d3c5fa4a201126cef75586296df9b4d2c62a0", 711661, JSON),
            "tokenizer_config.json": ("9261e7d79b44c8195c1cada2b453e55b00aeb81e907a6664974b4d7776172ab3", 366, JSON),
            # q8 runs on WASM; WebGPU needs fp16 (q8 gives wrong similarities there).
            "onnx/model_quantized.onnx": (
                "afdb6f1a0e45b715d0bb9b11772f032c399babd23bfc31fed1c170afc848bdb1", 22972370, ONNX,
            ),
            "onnx/model_fp16.onnx": (
                "2cdb5e58291813b6d6e248ed69010100246821a367fa17b1b81ae9483744533d", 45297825, ONNX,
            ),
        },
    },
}


def runtime_files():
    return [
        CatalogFile("runtime", name, ORT_CDN + name, sha, size, mimetype)
        for name, (sha, size, mimetype) in RUNTIME.items()
    ]


def task_files(task):
    spec = TASKS[task]
    base = f"https://huggingface.co/{spec['model']}/resolve/{spec['revision']}/"
    return [
        CatalogFile("models", f"{spec['model']}/{name}", base + name, sha, size, mimetype)
        for name, (sha, size, mimetype) in spec["files"].items()
    ]


def task_size(task):
    return sum(entry.size for entry in task_files(task))


def runtime_size():
    return sum(entry.size for entry in runtime_files())


def files(kind):
    return runtime_files() if kind == "runtime" else [e for task in TASKS for e in task_files(task)]


def version(kind):
    """Short fingerprint of every file of `kind`, part of their URLs.

    The files are served as immutable and browsers keep them in Cache Storage by URL: when
    a revision or a checksum changes, the URL changes too and nothing old is reused.
    """
    digest = hashlib.sha256()
    for entry in sorted(files(kind)):
        digest.update(f"{entry.path}\0{entry.sha256}\n".encode())
    return digest.hexdigest()[:12]


def find(kind, path):
    """Return the catalog entry served at /angels_runonweb/<kind>/<version>/<path>, or None."""
    return next((entry for entry in files(kind) if entry.path == path), None) if kind in KINDS else None
