import { onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

const SCROLL_THRESHOLD = 8;

/** Labels of the known systray items; unknown ones show their icon only. */
const SYSTRAY_LABELS = {
    "mail.messaging_menu": () => _t("Chat"),
    "mail.activity_menu": () => _t("Activity"),
    "discuss.CallMenu": () => _t("Call"),
    burger_menu: () => _t("Me"),
};

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.angelsBar = useState({ homeOpen: document.body.classList.contains("o_at_home_open") });
        this.angelsLabels = {
            home: _t("Home"),
            menu: _t("Menu"),
            search: _t("Search"),
        };
        // The home screen toggles a class on <body>; follow it for the
        // active tab without coupling the two components.
        const observer = new MutationObserver(() => {
            this.angelsBar.homeOpen = document.body.classList.contains("o_at_home_open");
        });
        observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
        // Hide the tab bar while scrolling down, show it again when scrolling up.
        this.angelsLastScroll = new WeakMap();
        const onScroll = (ev) => this.angelsOnScroll(ev);
        document.addEventListener("scroll", onScroll, { capture: true, passive: true });
        // A new view starts with the bar visible.
        const showBar = () => document.body.classList.remove("o_at_tab_bar_hidden");
        this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", showBar);
        onWillUnmount(() => {
            observer.disconnect();
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", showBar);
            document.removeEventListener("scroll", onScroll, { capture: true });
        });
    },

    get angelsHomeOpen() {
        return this.angelsBar.homeOpen;
    },

    angelsSystrayLabel(key) {
        return SYSTRAY_LABELS[key]?.() || "";
    },

    angelsOpenSections() {
        if (!this.currentApp || this.angelsHomeOpen) {
            this.angelsOpenHome();
            return;
        }
        this._openAppMenuSidebar();
    },

    angelsFocusSearch() {
        const input =
            document.querySelector(".o_at_home_search input") ||
            document.querySelector(".o_control_panel .o_searchview_input");
        if (input) {
            input.focus();
        } else {
            this.angelsOpenHome();
        }
    },

    angelsOnSystrayTab(ev) {
        // Tapping the label opens the item like tapping its icon.
        if (ev.target.closest(".o_at_tab_label")) {
            ev.currentTarget.querySelector("button, .dropdown-toggle, a")?.click();
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
