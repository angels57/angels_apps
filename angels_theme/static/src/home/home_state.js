import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

export const HOME_ACTION = "angels_theme.action_home";
const RECENTS_KEY = "angels_theme.recent_apps";
const MAX_RECENTS = 4;

/**
 * Whether the home screen was opened from an app. Going back (toggle
 * hotkey, Escape) only makes sense then: after loading /odoo/home directly
 * the previous history entry is not part of the web client.
 */
export const homeState = { cameFromApp: false };

export function readRecentApps() {
    try {
        const value = JSON.parse(browser.localStorage.getItem(RECENTS_KEY) || "[]");
        return Array.isArray(value) ? value : [];
    } catch {
        return [];
    }
}

/** Keeps the last apps opened on this device (xmlids, most recent first). */
const recentAppsService = {
    dependencies: ["menu"],
    start(env, { menu }) {
        env.bus.addEventListener("MENUS:APP-CHANGED", () => {
            const xmlid = menu.getCurrentApp()?.xmlid;
            if (!xmlid) {
                return;
            }
            const recents = [xmlid, ...readRecentApps().filter((x) => x !== xmlid)];
            try {
                browser.localStorage.setItem(RECENTS_KEY, JSON.stringify(recents.slice(0, MAX_RECENTS)));
            } catch {
                // Storage unavailable (private mode): the home screen shows no recents.
            }
        });
    },
};

registry.category("services").add("angels_theme_recent_apps", recentAppsService);
