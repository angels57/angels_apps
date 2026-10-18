import { NavBar } from "@web/webclient/navbar/navbar";
import { WebClient } from "@web/webclient/webclient";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { HOME_ACTION, homeState } from "./home_state";

export { HOME_ACTION };

/** Leave the home screen for the view it was opened from, if any. */
export function leaveHome() {
    if (homeState.cameFromApp) {
        homeState.cameFromApp = false;
        window.history.back();
    }
}

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.angelsAction = useService("action");
    },

    // The home button (and its hotkey) toggles the home screen.
    angelsOpenHome() {
        if (document.body.classList.contains("o_at_home_open")) {
            leaveHome();
            return;
        }
        homeState.cameFromApp = true;
        this.angelsAction.doAction(HOME_ACTION, { clearBreadcrumbs: true });
    },

    // On small screens, "All Apps" in the side menu opens the home screen too.
    onAllAppsBtnClick() {
        this._closeAppMenuSidebar();
        this.angelsOpenHome();
    },
});

patch(WebClient.prototype, {
    // `/odoo` without an action opens the home screen instead of the first app.
    _loadDefaultApp() {
        homeState.cameFromApp = false;
        return this.actionService.doAction(HOME_ACTION, { clearBreadcrumbs: true });
    },
});
