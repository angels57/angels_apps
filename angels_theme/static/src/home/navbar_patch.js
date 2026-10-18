import { NavBar } from "@web/webclient/navbar/navbar";
import { WebClient } from "@web/webclient/webclient";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

export const HOME_ACTION = "angels_theme.action_home";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.angelsAction = useService("action");
    },

    angelsOpenHome() {
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
        return this.actionService.doAction(HOME_ACTION, { clearBreadcrumbs: true });
    },
});
