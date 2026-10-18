import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";

/**
 * Every dialog (wizards, confirmations, forms opened in a dialog) shows the
 * icon and name of the app it was opened from (dialog.xml).
 */
patch(Dialog.prototype, {
    setup() {
        super.setup(...arguments);
        // Read once: the app does not change while a dialog is open.
        this.angelsApp = this.env.services.menu?.getCurrentApp?.() || null;
    },
});
