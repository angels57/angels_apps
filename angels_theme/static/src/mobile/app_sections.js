import { useState } from "@angels_theme/js/owl_compat";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

/**
 * Accordion of the current app's sections on phones (app_sections.xml).
 * Uses `angelsAction`, set up on the same NavBar by home/navbar_patch.js.
 */
patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.angelsSections = useState({ openGroupId: null });
        this.angelsCloseLabel = _t("Close menu");
    },

    _openAppMenuSidebar() {
        super._openAppMenuSidebar(...arguments);
        if (this.state.isAppMenuSidebarOpened) {
            // Start with the group of the current view open, the rest folded.
            const current = this.angelsCurrentMenuId();
            const group = this.currentAppSections.find(
                (section) => section.childrenTree.length && this.angelsContainsMenu(section, current)
            );
            this.angelsSections.openGroupId = group ? group.id : null;
        }
    },

    angelsCurrentMenuId() {
        const actionId = this.angelsAction?.currentController?.action?.id;
        if (!actionId || !this.currentApp) {
            return null;
        }
        // The app's root menu usually opens the same action as its first
        // option: skip it, and prefer an option without children.
        const matches = this.menuService
            .getAll()
            .filter(
                (menu) =>
                    menu.appID === this.currentApp.id &&
                    menu.id !== this.currentApp.id &&
                    menu.actionID === actionId
            );
        const match = matches.find((menu) => !menu.children.length) || matches[0];
        return match?.id ?? null;
    },

    angelsContainsMenu(section, menuId) {
        return (
            section.id === menuId ||
            section.childrenTree.some((child) => this.angelsContainsMenu(child, menuId))
        );
    },

    angelsIsCurrentMenu(menu) {
        return menu.id === this.angelsCurrentMenuId();
    },

    angelsIsGroupOpen(section) {
        return this.angelsSections.openGroupId === section.id;
    },

    angelsToggleGroup(section) {
        this.angelsSections.openGroupId = this.angelsIsGroupOpen(section) ? null : section.id;
    },

    angelsLeafCount(section) {
        return section.childrenTree.reduce(
            (count, child) => count + (child.childrenTree.length ? this.angelsLeafCount(child) : 1),
            0
        );
    },

    /** Configuration groups are shown in grey, as in the mockup. */
    angelsIsConfigMenu(section) {
        return /config/i.test(section.xmlid || "");
    },
});
