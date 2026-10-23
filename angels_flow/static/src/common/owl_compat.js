/**
 * The few Owl APIs that differ between Odoo 19 (Owl 2) and Odoo 20 (Owl 3).
 * This file is the only one that changes between the 19.0 and 20.0 branches.
 */
import { reactive, useComponent, useState } from "@odoo/owl";

/** Reactive object: a component that reads it through `useState` re-renders when it changes. */
export { reactive, useState };

/** Props of the current component (call it in `setup`); Owl 2 already set them on the component. */
export const useProps = () => useComponent().props;
