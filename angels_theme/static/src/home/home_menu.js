import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { fuzzyLookup } from "@web/core/utils/search";
import { session } from "@web/session";
import { useExternalListener, useState } from "@angels_theme/js/owl_compat";

const GRID_COLUMNS = 6;

/**
 * Full screen app launcher: a grid of the root menus and a search box that
 * also finds every submenu ("Sales / Orders / Quotations").
 */
export class HomeMenu extends Component {
    static template = "angels_theme.HomeMenu";

    setup() {
        this.menuService = useService("menu");
        // `focused` stays -1 until the keyboard is used, so no tile looks selected.
        this.state = useState({ query: "", focused: -1 });
        this.apps = this.menuService.getApps();
        this.entries = this.computeEntries();
        useExternalListener(window, "keydown", this.onWindowKeydown.bind(this));
        // The background covers the whole client, navbar included.
        const bodyClasses = ["o_at_home_open", `o_at_home_bg_${this.background}`];
        onMounted(() => {
            document.body.classList.add(...bodyClasses);
            const image = session.angels_theme?.home_image_url;
            if (this.background === "image" && image) {
                document.body.style.setProperty("--at-home-image", `url('${image}')`);
            }
        });
        onWillUnmount(() => {
            document.body.classList.remove(...bodyClasses);
            document.body.style.removeProperty("--at-home-image");
        });
    }

    get background() {
        return session.angels_theme?.home_background || "dots";
    }

    get searchPlaceholder() {
        return _t("Search apps and menus...");
    }

    get results() {
        const query = this.state.query.trim();
        return query ? fuzzyLookup(query, this.entries, (entry) => entry.label).slice(0, 12) : [];
    }

    /** Leaf menus that open an action, labelled with their full path. */
    computeEntries() {
        const entries = [];
        const visit = (menu, parents) => {
            const path = [...parents, menu.name];
            if (menu.actionID) {
                entries.push({ id: menu.id, menu, app: this.menuService.getMenu(menu.appID), label: path.join(" / ") });
            }
            for (const child of menu.childrenTree || []) {
                visit(child, path);
            }
        };
        for (const app of this.apps) {
            visit(this.menuService.getMenuAsTree(app.id), []);
        }
        return entries;
    }

    initial(app) {
        return (app.name || "?").trim().charAt(0).toUpperCase();
    }

    open(menu) {
        this.menuService.selectMenu(menu);
    }

    onInput(ev) {
        this.state.query = ev.target.value;
        this.state.focused = 0;
    }

    moveFocus(delta) {
        const size = this.state.query.trim() ? this.results.length : this.apps.length;
        if (size) {
            const from = this.state.focused < 0 ? 0 : this.state.focused + delta;
            this.state.focused = Math.min(Math.max(from, 0), size - 1);
        }
    }

    onWindowKeydown(ev) {
        if (ev.altKey || ev.ctrlKey || ev.metaKey) {
            return;
        }
        const searching = Boolean(this.state.query.trim());
        const step = searching ? 1 : GRID_COLUMNS;
        const moves = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -step, ArrowDown: step };
        if (ev.key in moves && !(searching && ["ArrowLeft", "ArrowRight"].includes(ev.key))) {
            ev.preventDefault();
            this.moveFocus(moves[ev.key]);
        } else if (ev.key === "Enter") {
            const target = searching ? this.results[this.state.focused]?.menu : this.apps[this.state.focused];
            if (target) {
                ev.preventDefault();
                this.open(target);
            }
        } else if (ev.key === "Escape") {
            if (searching) {
                this.state.query = "";
                this.state.focused = -1;
            } else {
                window.history.back();
            }
        } else if (ev.key.length === 1 && ev.target.tagName !== "INPUT") {
            // Typing anywhere starts a search.
            const input = document.querySelector(".o_at_home_search input");
            input?.focus();
        }
    }
}

registry.category("actions").add("angels_theme.home", HomeMenu);
