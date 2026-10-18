import { onWillUnmount } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";

const SHEET = ".o-mail-systrayFullscreenDropdownMenu";
const HANDLE_HEIGHT = 32;
const CLOSE_DISTANCE = 80;
const CLOSE_DURATION = 220;

const reducedMotion = () => browser.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/**
 * Phones: the full screen systray menus (chat, activity) become a bottom
 * sheet (systray_sheet.scss). This adds its title, the closing animation
 * and closing by dragging its handle down. Builds on mobile_tab_bar.js.
 */
patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        const onPointerDown = (ev) => this.angelsOnSheetPointerDown(ev);
        document.addEventListener("pointerdown", onPointerDown);
        // A tap on the backdrop closes the sheet with its animation. Odoo
        // closes menus on any pointerdown outside them (window, capture);
        // this listener is registered first, so it can keep that one from
        // closing the menu at once.
        const onBackdrop = (ev) => {
            if (ev.target.closest?.(".o_at_systray_backdrop")) {
                ev.stopImmediatePropagation();
                ev.preventDefault();
                this.angelsCloseSystrayMenu();
            }
        };
        window.addEventListener("pointerdown", onBackdrop, { capture: true });
        onWillUnmount(() => {
            window.removeEventListener("pointerdown", onBackdrop, { capture: true });
            document.removeEventListener("pointerdown", onPointerDown);
            document.body.classList.remove("o_at_systray_open");
        });
    },

    angelsSyncSystray() {
        super.angelsSyncSystray(...arguments);
        if (!this.ui.isSmall) {
            return;
        }
        const open = this.angelsSystrayEntries().find((entry) => entry.expanded);
        document.body.classList.toggle("o_at_systray_open", Boolean(open));
        // Sheet title, drawn by CSS from this (translated) label.
        document.body.style.setProperty("--at-sheet-title", JSON.stringify(open ? open.label : ""));
    },

    angelsToggleMore() {
        if (this.angelsBar.systrayOpen) {
            this.angelsCloseSystrayMenu();
            return;
        }
        super.angelsToggleMore(...arguments);
    },

    /** Slide the open sheet down, then close its menu. */
    angelsCloseSystrayMenu() {
        const sheet = document.querySelector(SHEET);
        if (sheet?.classList.contains("o_at_sheet_closing")) {
            return;
        }
        const close = () => {
            const open = this.angelsSystrayEntries().find((entry) => entry.expanded);
            if (open) {
                // The sheet stays down until Odoo removes it.
                open.toggler.click();
            } else {
                sheet?.classList.remove("o_at_sheet_closing");
            }
        };
        if (!sheet || reducedMotion()) {
            close();
            return;
        }
        // From where it is (it may be half dragged) down and out.
        sheet.classList.add("o_at_sheet_closing");
        browser.setTimeout(close, CLOSE_DURATION);
    },

    /** Dragging the top of the sheet (its handle and title) down closes it. */
    angelsOnSheetPointerDown(ev) {
        const sheet = ev.target.closest?.(SHEET);
        if (!this.ui.isSmall || !sheet || ev.clientY - sheet.getBoundingClientRect().top > HANDLE_HEIGHT) {
            return;
        }
        const startY = ev.clientY;
        sheet.classList.add("o_at_sheet_dragging");
        const onMove = (moveEv) => {
            const distance = Math.max(0, moveEv.clientY - startY);
            sheet.style.transform = `translateY(${distance}px)`;
        };
        const onEnd = (endEv) => {
            document.removeEventListener("pointermove", onMove);
            document.removeEventListener("pointerup", onEnd);
            document.removeEventListener("pointercancel", onEnd);
            sheet.classList.remove("o_at_sheet_dragging");
            if (endEv.type === "pointerup" && endEv.clientY - startY > CLOSE_DISTANCE) {
                this.angelsCloseSystrayMenu();
            } else {
                sheet.style.removeProperty("transform");
            }
        };
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onEnd);
        document.addEventListener("pointercancel", onEnd);
    },
});
