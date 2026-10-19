import { Component, onMounted, onWillStart, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { fuzzyLookup } from "@web/core/utils/search";
import { session } from "@web/session";
import { useExternalListener, useState } from "@angels_theme/js/owl_compat";
import { readRecentApps } from "./home_state";
import { leaveHome } from "./navbar_patch";

const GRID_COLUMNS = 6;
const EMPTY_PREFS = { favorites: [], order: [] };

/**
 * Full screen app launcher: a grid of the root menus and a search box that
 * also finds every submenu ("Sales / Orders / Quotations").
 *
 * The user can pin apps (they come first) and drag tiles to reorder them;
 * both are saved on the user. The last apps opened on this device show in a
 * "Recent" row, and tiles carry counters from `res.users.angels_home_badges`.
 */
export class HomeMenu extends Component {
    static template = "angels_theme.HomeMenu";

    setup() {
        this.menuService = useService("menu");
        this.orm = useService("orm");
        const prefs = session.angels_theme?.home_prefs || EMPTY_PREFS;
        // `focused` stays -1 until the keyboard is used, so no tile looks selected.
        this.state = useState({
            query: "",
            focused: -1,
            favorites: [...(prefs.favorites || [])],
            order: [...(prefs.order || [])],
            badges: {},
            dragging: null,
        });
        this.allApps = this.menuService.getApps();
        this.entries = this.computeEntries();
        this.recentXmlids = readRecentApps();
        useExternalListener(window, "keydown", this.onWindowKeydown.bind(this));
        onWillStart(() => this.loadBadges());
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

    /** Pinned apps first, then the rest; each group follows the saved order. */
    get apps() {
        const rank = (app) => {
            const index = this.state.order.indexOf(app.xmlid);
            return index < 0 ? this.state.order.length + this.allApps.indexOf(app) : index;
        };
        const sorted = [...this.allApps].sort((a, b) => rank(a) - rank(b));
        return [...sorted.filter((app) => this.isFavorite(app)), ...sorted.filter((app) => !this.isFavorite(app))];
    }

    get recentApps() {
        // Off unless the user turns it on in their preferences.
        if (!session.angels_theme?.home_show_recents) {
            return [];
        }
        return this.recentXmlids
            .map((xmlid) => this.allApps.find((app) => app.xmlid === xmlid))
            .filter(Boolean);
    }

    get hasCustomLayout() {
        return Boolean(this.state.favorites.length || this.state.order.length);
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
        for (const app of this.allApps) {
            visit(this.menuService.getMenuAsTree(app.id), []);
        }
        return entries;
    }

    async loadBadges() {
        try {
            this.state.badges = await this.orm.call("res.users", "angels_home_badges", []);
        } catch {
            // Counters are a nice-to-have: the home screen works without them.
            this.state.badges = {};
        }
    }

    badge(app) {
        const count = this.state.badges[app.xmlid] || 0;
        return count > 99 ? "99+" : count;
    }

    initial(app) {
        return (app.name || "?").trim().charAt(0).toUpperCase();
    }

    isFavorite(app) {
        return this.state.favorites.includes(app.xmlid);
    }

    pinTitle(app) {
        return this.isFavorite(app) ? _t("Unpin") : _t("Pin to the top");
    }

    open(menu) {
        this.menuService.selectMenu(menu);
    }

    // = Layout

    async savePrefs() {
        const prefs = { favorites: [...this.state.favorites], order: [...this.state.order] };
        if (session.angels_theme) {
            // Keep the session in sync so reopening the home screen shows it.
            session.angels_theme.home_prefs = prefs;
        }
        await this.orm.call("res.users", "angels_home_save_prefs", [prefs]);
    }

    toggleFavorite(app) {
        this.state.favorites = this.isFavorite(app)
            ? this.state.favorites.filter((xmlid) => xmlid !== app.xmlid)
            : [...this.state.favorites, app.xmlid];
        this.savePrefs();
    }

    resetLayout() {
        this.state.favorites = [];
        this.state.order = [];
        this.savePrefs();
    }

    // = Drag and drop (native HTML5, desktop)

    onDragStart(ev, app) {
        this.state.dragging = app.xmlid;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", app.xmlid);
    }

    onDragOver(ev, app) {
        if (this.state.dragging && this.state.dragging !== app.xmlid) {
            ev.preventDefault();
            ev.dataTransfer.dropEffect = "move";
        }
    }

    onDrop(ev, target) {
        ev.preventDefault();
        const moved = this.state.dragging;
        this.state.dragging = null;
        if (!moved || moved === target.xmlid) {
            return;
        }
        const order = this.apps.map((app) => app.xmlid).filter((xmlid) => xmlid !== moved);
        order.splice(order.indexOf(target.xmlid), 0, moved);
        this.state.order = order;
        if (this.state.favorites.length) {
            // Within the pinned group the order follows the same list.
            this.state.favorites = order.filter((xmlid) => this.state.favorites.includes(xmlid));
        }
        this.savePrefs();
    }

    onDragEnd() {
        this.state.dragging = null;
    }

    // = Keyboard

    onInput(ev) {
        this.state.query = ev.target.value;
        this.state.focused = 0;
    }

    moveFocus(delta) {
        const size = this.state.query.trim() ? this.results.length : this.allApps.length;
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
                leaveHome();
            }
        } else if (ev.key.length === 1 && ev.target.tagName !== "INPUT") {
            // Typing anywhere starts a search.
            const input = document.querySelector(".o_at_home_search input");
            input?.focus();
        }
    }
}

registry.category("actions").add("angels_theme.home", HomeMenu);
