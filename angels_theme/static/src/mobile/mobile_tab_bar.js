import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import { useState } from "@angels_theme/js/owl_compat";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

const SCROLL_THRESHOLD = 8;

/** Known systray items of the tab bar; others use their own title. */
const SYSTRAY_ITEMS = {
    "mail.messaging_menu": { label: () => _t("Chat"), icon: "chat" },
    "mail.activity_menu": { label: () => _t("Activity"), icon: "clock" },
    "discuss.CallMenu": { label: () => _t("Call"), icon: "phone" },
    burger_menu: { label: () => _t("Profile"), icon: "user" },
};

const ICON_PATHS = {
    chat: "M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
    clock: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3 2",
    phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
    user: "M12 12a4 4 0 1 0 0-8a4 4 0 1 0 0 8zM4 21a8 8 0 0 1 16 0",
    dot: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z",
};

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.angelsBar = useState({
            homeOpen: document.body.classList.contains("o_at_home_open"),
            systrayItems: [],
            systrayOpen: false,
        });
        this.angelsLabels = {
            home: _t("Home"),
            menu: _t("Menu"),
            search: _t("Search"),
        };
        // The home screen toggles a class on <body>; follow it for the
        // active tab without coupling the two components.
        const bodyObserver = new MutationObserver(() => {
            this.angelsBar.homeOpen = document.body.classList.contains("o_at_home_open");
        });
        bodyObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
        // Counters and open state of the (hidden) systray items, for their tabs.
        const systrayObserver = new MutationObserver(() => this.angelsSyncSystray());
        onMounted(() => {
            const systray = document.querySelector(".o_main_navbar .o_menu_systray");
            if (systray) {
                systrayObserver.observe(systray, {
                    subtree: true,
                    childList: true,
                    characterData: true,
                    attributes: true,
                    attributeFilter: ["aria-expanded", "class"],
                });
            }
            this.angelsSyncSystray();
        });
        // A render may have been computed before the last systray change:
        // set the active tabs from the togglers again once it is applied.
        onPatched(() => this.angelsApplyActiveTabs());
        // Hide the tab bar while scrolling down, show it again when scrolling up.
        this.angelsLastScroll = new WeakMap();
        const onScroll = (ev) => this.angelsOnScroll(ev);
        document.addEventListener("scroll", onScroll, { capture: true, passive: true });
        // A new view starts with the bar visible.
        const onViewChange = () => document.body.classList.remove("o_at_tab_bar_hidden");
        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", onViewChange);
        onWillUnmount(() => {
            bodyObserver.disconnect();
            systrayObserver.disconnect();
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", onViewChange);
            document.removeEventListener("scroll", onScroll, { capture: true });
        });
    },

    get angelsHomeOpen() {
        return this.angelsBar.homeOpen;
    },

    angelsBadge(count) {
        return count > 99 ? "99+" : count;
    },

    angelsIconPath(icon) {
        return ICON_PATHS[icon] || ICON_PATHS.dot;
    },

    // = Systray items (read from their own, hidden, DOM)

    angelsSystrayEntries() {
        const entries = [];
        for (const wrapper of document.querySelectorAll(".o_main_navbar .o_at_systray_item")) {
            const toggler = wrapper.querySelector("button, a");
            const root = wrapper.firstElementChild;
            // Skip items with nothing to show on phones: the call menu outside
            // a call, and items Odoo hides below md (`d-none d-md-block`).
            if (!toggler || !root || getComputedStyle(root).display === "none") {
                continue;
            }
            const key = wrapper.dataset.key;
            const known = SYSTRAY_ITEMS[key];
            entries.push({
                key,
                toggler,
                label: known?.label() || toggler.title || toggler.getAttribute("aria-label") || key,
                icon: known?.icon || "dot",
                avatar: wrapper.querySelector("img")?.getAttribute("src"),
                count: parseInt(wrapper.querySelector(".badge")?.textContent, 10) || 0,
                expanded: toggler.getAttribute("aria-expanded") === "true",
            });
        }
        return entries;
    },

    angelsSyncSystray() {
        if (!this.ui.isSmall) {
            return;
        }
        const entries = this.angelsSystrayEntries();
        const open = entries.some((entry) => entry.expanded);
        this.angelsBar.systrayItems = entries.map(({ toggler, ...entry }) => entry);
        this.angelsBar.systrayOpen = open;
        this.angelsApplyActiveTabs(entries);
    },

    /**
     * Highlight the tab of the open systray menu, or the app tab, straight
     * on the DOM: the navbar re-renders only once its systray components
     * have (~0.3s with Discuss), which would make the highlight lag.
     */
    angelsApplyActiveTabs(entries = this.angelsSystrayEntries()) {
        if (!this.ui.isSmall) {
            return;
        }
        const open = entries.some((entry) => entry.expanded);
        for (const tab of document.querySelectorAll(".o_main_navbar .o_at_tab_systray")) {
            const expanded = entries.some((entry) => entry.key === tab.dataset.key && entry.expanded);
            tab.classList.toggle("o_at_tab_active", expanded);
        }
        document
            .querySelector(".o_main_navbar .o_at_tab_app")
            ?.classList.toggle("o_at_tab_active", !this.angelsHomeOpen && Boolean(this.currentApp) && !open);
    },

    /**
     * Tab of a systray item: opens its menu, closes it when it is the open
     * one, or switches from the open one to it.
     */
    angelsOnSystrayTab(key) {
        const entries = this.angelsSystrayEntries();
        const target = entries.find((entry) => entry.key === key);
        if (!target) {
            return;
        }
        if (target.expanded) {
            this.angelsCloseSystrayMenu();
            return;
        }
        entries.find((entry) => entry.expanded)?.toggler.click();
        target.toggler.click();
    },

    angelsCloseSystrayMenu() {
        this.angelsSystrayEntries()
            .find((entry) => entry.expanded)
            ?.toggler.click();
    },

    // = Tabs

    angelsOpenSections() {
        if (!this.currentApp || this.angelsHomeOpen) {
            this.angelsOpenHome();
            return;
        }
        this._openAppMenuSidebar();
    },

    /**
     * Focus the search box of the current view. On phones Odoo hides it
     * behind a magnifier button in the control panel: open it first.
     */
    async angelsFocusSearch() {
        const homeInput = document.querySelector(".o_at_home_search input");
        if (homeInput) {
            homeInput.focus();
            return;
        }
        const panel = document.querySelector(".o_action_manager .o_control_panel");
        if (!panel) {
            return;
        }
        let input = panel.querySelector(".o_searchview_input");
        if (!input) {
            const toggler = [...panel.querySelectorAll("button")].find((button) =>
                button.querySelector(".fa-search")
            );
            toggler?.click();
            for (let i = 0; i < 20 && toggler && !input; i++) {
                await wait(50);
                input = panel.querySelector(".o_searchview_input");
            }
        }
        if (input) {
            input.focus();
            input.scrollIntoView({ block: "nearest" });
        }
    },

    angelsOnScroll(ev) {
        if (!this.ui.isSmall) {
            return;
        }
        const target = ev.target === document ? document.scrollingElement : ev.target;
        if (!target || typeof target.scrollTop !== "number") {
            return;
        }
        const previous = this.angelsLastScroll.get(target) ?? 0;
        const delta = target.scrollTop - previous;
        if (Math.abs(delta) < SCROLL_THRESHOLD) {
            return;
        }
        this.angelsLastScroll.set(target, target.scrollTop);
        const hide = delta > 0 && target.scrollTop > 40;
        document.body.classList.toggle("o_at_tab_bar_hidden", hide);
    },
});
