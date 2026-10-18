import { Notebook } from "@web/core/notebook/notebook";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";

const X2MANY = ["one2many", "many2many"];

patch(Notebook.prototype, {
    setup() {
        super.setup(...arguments);
        // Reopen the last tab of this form, unless the view asks for a page.
        const key = this.angelsStorageKey;
        if (key && !this.props.defaultPage) {
            const saved = browser.localStorage.getItem(key);
            if (saved && this.navItems.some((item) => item[0] === saved)) {
                this.state.currentPage = saved;
            }
        }
    },

    async activatePage(pageIndex) {
        await super.activatePage(...arguments);
        const key = this.angelsStorageKey;
        if (key && this.state.currentPage === pageIndex) {
            browser.localStorage.setItem(key, pageIndex);
        }
    },

    get angelsStorageKey() {
        const resModel = this.env.model?.root?.resModel;
        if (!resModel || this.props.orientation !== "horizontal") {
            return null;
        }
        // Odoo 20 turned `pages` into a computed signal.
        const pages = typeof this.pages === "function" ? this.pages() : this.pages;
        const ids = pages.map((page) => page[0]).join(",");
        return `angels_theme.tab:${resModel}:${ids}`;
    },

    /**
     * Number of records of the page's list, when the page holds exactly one
     * one2many or many2many field. Returns null otherwise.
     */
    angelsTabCount(page) {
        const root = this.env.model?.root;
        if (!root || !page.fieldNames) {
            return null;
        }
        const lists = page.fieldNames.filter((name) =>
            X2MANY.includes(root.fields[name]?.type)
        );
        if (lists.length !== 1) {
            return null;
        }
        return root.data[lists[0]]?.count ?? null;
    },
});
