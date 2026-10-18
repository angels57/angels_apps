/**
 * The few Owl APIs that differ between Odoo 19 (Owl 2) and Odoo 20 (Owl 3).
 * This file is the only one that changes between the 19.0 and 20.0 branches.
 */
import { proxy, useProps as owlUseProps } from "@odoo/owl";

/** Reactive object: a component that reads it in its template re-renders when it changes. */
export const reactive = proxy;

/** Owl 3 subscribes a render to every proxy it reads: a proxy is all the state needs. */
export const useState = (state) => proxy(state);

/** Props of the current component (call it in `setup`); Owl 3 ignores `static props`. */
export const useProps = () => owlUseProps();
