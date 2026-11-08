import { detectWebGPU } from "../core/loader";
import { labLabels } from "./lab_labels";
import { examples, LAB_TASKS } from "./lab_tasks";
import { clearModelCache, errorMessage, esc, formatBytes, modelCacheSize } from "./lab_utils";

const now = () => performance.now();

// Diagnostics of the browser and the server, plus one panel per task, drawn with plain DOM.
export class LabPage {
    constructor(root, { call, runonweb, probe = {} }) {
        this.root = root;
        this.call = call;
        this.runonweb = runonweb;
        this.probe = {
            webgpu: detectWebGPU,
            isolated: () => Boolean(globalThis.crossOriginIsolated),
            cacheSize: modelCacheSize,
            clearCache: clearModelCache,
            ...probe,
        };
        this.t = labLabels();
        this.status = null;
        this.busy = false;
        this.onClick = this.onClick.bind(this);
        this.onInput = this.onInput.bind(this);
    }

    async start() {
        const t = this.t;
        this.root.innerHTML = `<div class="o-row">
            <header class="o-row-top">
                <div><h1 class="o-row-title">${esc(t["RunOnWeb Lab"])}</h1>
                <p class="o-row-lead">${esc(t["Try each task in this browser. Texts and images are processed on this device."])}</p></div>
                <button type="button" class="o-row-btn o-row-primary" data-act="test-all">${esc(t["Test all"])}</button>
            </header>
            <div class="o-row-summary" data-role="summary" aria-live="polite"></div>
            <section class="o-row-grid">
                <div class="o-row-card" data-role="browser"></div>
                <div class="o-row-card" data-role="server"></div>
            </section>
            <section class="o-row-tasks" data-role="tasks"></section>
        </div>`;
        this.root.addEventListener("click", this.onClick);
        this.root.addEventListener("input", this.onInput);
        this.unsubscribe = this.runonweb.onProgress((info) => this.showProgress(info));
        await Promise.all([this.renderBrowser(), this.refresh()]);
    }

    destroy() {
        this.unsubscribe?.();
        this.root.removeEventListener("click", this.onClick);
        this.root.removeEventListener("input", this.onInput);
        this.root.replaceChildren();
    }

    $(selector) {
        return this.root.querySelector(selector);
    }

    panel(task) {
        return this.$(`[data-task="${task}"]`);
    }

    async refresh() {
        this.status = await this.call("get_status");
        this.renderServer();
        this.renderTasks();
    }

    async renderBrowser() {
        const t = this.t;
        const [webgpu, cache] = await Promise.all([this.probe.webgpu(), this.probe.cacheSize().catch(() => 0)]);
        this.$('[data-role="browser"]').innerHTML = `<h2>${esc(t["This browser"])}</h2>
            <dl class="o-row-facts">
                <dt>WebGPU</dt><dd data-fact="webgpu">${esc(webgpu ? t["Available"] : t["Not available, WASM will be used"])}</dd>
                <dt>${esc(t["Threads"])}</dt><dd data-fact="threads">${esc(this.probe.isolated() ? t["Several"] : t["One (the page is not cross-origin isolated)"])}</dd>
                <dt>${esc(t["Model cache"])}</dt><dd data-fact="cache">${esc(formatBytes(cache))}</dd>
            </dl>
            <button type="button" class="o-row-btn" data-act="clear-cache">${esc(t["Clear the model cache"])}</button>`;
    }

    renderServer() {
        const t = this.t;
        const s = this.status;
        this.$('[data-role="server"]').innerHTML = `<h2>${esc(t["This server"])}</h2>
            <dl class="o-row-facts">
                <dt>${esc(t["Internet downloads"])}</dt><dd data-fact="remote">${esc(s.allowRemote ? t["Allowed"] : t["Off"])}</dd>
                <dt>${esc(t["Device"])}</dt><dd data-fact="device">${esc(s.device)}</dd>
                <dt>ONNX Runtime</dt>
                <dd data-fact="runtime">${esc(s.runtime.local ? t["On the server"] : t["Not downloaded"])} · ${esc(formatBytes(s.runtime.size))}, ${esc(t["shared by every task"])}<br/><code>${esc(s.runtime.version)}</code></dd>
                <dt>${esc(t["Storage folder"])}</dt><dd><code>${esc(s.storage)}</code></dd>
            </dl>`;
    }

    renderTasks() {
        const t = this.t;
        // Keep what was typed when the panels are drawn again.
        const typed = {};
        for (const el of this.root.querySelectorAll("[data-task] [data-field]")) {
            typed[`${el.closest("[data-task]").dataset.task}:${el.dataset.field}`] = el.value;
        }
        this.$('[data-role="tasks"]').innerHTML = Object.entries(this.status.tasks)
            .filter(([task]) => LAB_TASKS[task])
            .map(([task, state]) => {
                const ui = LAB_TASKS[task];
                const badge = state.local ? "On the server" : state.available ? "From the internet" : "Not available";
                return `<article class="o-row-card o-row-task" data-task="${esc(task)}">
                    <header class="o-row-task-head">
                        <h3>${esc(t[ui.title])}</h3>
                        <span class="o-row-badge o-row-badge-${state.local ? "ok" : state.available ? "info" : "off"}" data-role="badge">${esc(t[badge])}</span>
                    </header>
                    <p class="o-row-meta"><code>${esc(state.model)}</code> · <a href="${esc(state.licenseUrl)}" target="_blank" rel="noopener">${esc(state.license)}</a> · ${esc(formatBytes(state.size))}</p>
                    ${state.available ? "" : `<p class="o-row-hint">${esc(t["To run it, download it to the server or allow internet downloads in Settings."])}</p>`}
                    <div class="o-row-actions">${state.local
                        ? `<button type="button" class="o-row-btn" data-act="remove">${esc(t["Remove from the server"])}</button>`
                        : `<button type="button" class="o-row-btn" data-act="download">${esc(t["Download to the server"])}</button>`}</div>
                    ${ui.fields.map((field) => {
                        const id = `o-row-${esc(task)}-${esc(field.name)}`;
                        const value = typed[`${task}:${field.name}`] ?? field.example;
                        return `<label class="o-row-label" for="${id}">${esc(t[field.label])}</label>
                            <textarea class="o-row-input" id="${id}" data-field="${esc(field.name)}" rows="${field.rows}">${esc(value)}</textarea>`;
                    }).join("")}
                    <div class="o-row-error" data-role="error" role="alert"></div>
                    <div class="o-row-actions">
                        <button type="button" class="o-row-btn o-row-primary" data-act="run" ${state.available ? "" : "disabled"}>${esc(t["Run"])}</button>
                        <button type="button" class="o-row-btn" data-act="example">${esc(t["Use the example"])}</button>
                    </div>
                    <div class="o-row-progress" data-role="progress" hidden><span class="o-row-bar"><span data-role="bar"></span></span><small data-role="progress-text"></small></div>
                    <div class="o-row-result" data-role="result"></div>
                </article>`;
            })
            .join("");
    }

    showProgress({ task, status, progress }) {
        const panel = this.panel(task);
        const box = panel?.querySelector('[data-role="progress"]');
        if (!box) {
            return;
        }
        const t = this.t;
        box.hidden = false;
        const pct = typeof progress === "number" ? Math.max(0, Math.min(100, progress)) : null;
        box.querySelector('[data-role="bar"]').style.width = `${pct ?? 100}%`;
        const label = status === "progress" ? t["Downloading"] : status === "ready" || status === "done" ? t["Done"] : t["Working"];
        box.querySelector('[data-role="progress-text"]').textContent = pct === null ? label : `${label} ${Math.round(pct)}%`;
    }

    setError(task, message) {
        const box = this.panel(task)?.querySelector('[data-role="error"]');
        if (box) {
            box.textContent = message || "";
        }
    }

    // Loads the task (timed apart from the run) and runs it on `input`.
    async execute(task, input) {
        const startLoad = now();
        const instance = await this.runonweb.load(task);
        const loadMs = now() - startLoad;
        const startRun = now();
        const result = await this.runonweb.run(task, input);
        return { result, loadMs, runMs: now() - startRun, device: instance.device || "" };
    }

    values(task) {
        const fields = this.panel(task).querySelectorAll("[data-field]");
        return Object.fromEntries([...fields].map((el) => [el.dataset.field, el.value]));
    }

    async runTask(task) {
        const panel = this.panel(task);
        const ui = LAB_TASKS[task];
        const values = this.values(task);
        const problem = ui.validate(values);
        if (problem) {
            this.setError(task, this.t[problem]);
            return;
        }
        const input = ui.toInput(values);
        this.setError(task, "");
        const resultBox = panel.querySelector('[data-role="result"]');
        resultBox.textContent = this.t["Loading the model"];
        try {
            const out = await this.execute(task, input);
            resultBox.innerHTML = `${ui.renderResult(out.result)}${this.metricsHtml(out)}`;
        } catch (error) {
            resultBox.textContent = "";
            this.setError(task, errorMessage(error));
        }
    }

    metricsHtml({ loadMs, runMs, device }) {
        const t = this.t;
        return `<dl class="o-row-facts o-row-metrics">
            <dt>${esc(t["Load"])}</dt><dd data-metric="load">${Math.round(loadMs)} ms</dd>
            <dt>${esc(t["Run time"])}</dt><dd data-metric="run">${Math.round(runMs)} ms</dd>
            <dt>${esc(t["Device"])}</dt><dd data-metric="device">${esc(device)}</dd>
        </dl>`;
    }

    async testAll() {
        const t = this.t;
        const summary = this.$('[data-role="summary"]');
        summary.textContent = t["Testing"];
        const rows = [];
        for (const [task, state] of Object.entries(this.status.tasks)) {
            const ui = LAB_TASKS[task];
            if (!ui) {
                continue;
            }
            if (!state.available) {
                rows.push([task, "off", t["Not available"]]);
                continue;
            }
            try {
                const out = await this.execute(task, ui.toInput(examples(ui)));
                rows.push([task, "ok", `${ui.summary(out.result)} · ${Math.round(out.runMs)} ms`]);
            } catch (error) {
                rows.push([task, "fail", `${t["Failed"]}: ${errorMessage(error)}`]);
            }
        }
        summary.innerHTML = `<ul>${rows.map(([task, kind, text]) =>
            `<li class="o-row-summary-${kind}" data-summary="${esc(task)}"><strong>${esc(t[LAB_TASKS[task].title])}</strong> ${esc(text)}</li>`).join("")}</ul>`;
    }

    async serverAction(method, task) {
        try {
            this.status = await this.call(method, task);
            await this.runonweb.getConfig(true);
            this.renderServer();
            this.renderTasks();
        } catch (error) {
            this.setError(task, errorMessage(error));
        }
    }

    async onClick(ev) {
        const button = ev.target.closest("[data-act]");
        if (!button || this.busy) {
            return;
        }
        const task = button.closest("[data-task]")?.dataset.task;
        const act = button.dataset.act;
        if (act === "example") {
            for (const [name, value] of Object.entries(examples(LAB_TASKS[task]))) {
                this.panel(task).querySelector(`[data-field="${name}"]`).value = value;
            }
            this.setError(task, "");
            return;
        }
        this.busy = true;
        this.root.classList.add("o-row-busy");
        try {
            if (act === "run") {
                await this.runTask(task);
            } else if (act === "test-all") {
                await this.testAll();
            } else if (act === "download") {
                await this.serverAction("download_task", task);
            } else if (act === "remove") {
                await this.serverAction("remove_task", task);
            } else if (act === "clear-cache") {
                await this.runonweb.dispose();
                await this.probe.clearCache();
                await this.renderBrowser();
                this.$('[data-role="summary"]').textContent = this.t["The model cache of this browser is empty."];
            }
        } finally {
            this.busy = false;
            this.root.classList.remove("o-row-busy");
        }
    }

    onInput(ev) {
        const task = ev.target.closest("[data-task]")?.dataset.task;
        if (task) {
            this.setError(task, "");
        }
    }
}
