/**
 * The few Owl APIs that differ between Odoo 19 (Owl 2) and Odoo 20 (Owl 3).
 * This file is the only JS one that changes between the 19.0 and 20.0 branches.
 */
import { proxy, useListener } from "@odoo/owl";

/** Owl 3 subscribes a render to every proxy it reads: a proxy is all the state needs. */
export const useState = (state) => proxy(state);

/** Listener on a global target (window, document), removed with the component. Pass a bound handler. */
export const useExternalListener = (target, eventName, handler) =>
    useListener(target, eventName, handler);
