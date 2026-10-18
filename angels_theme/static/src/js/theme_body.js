import { session } from "@web/session";

// Apply the user's theme preferences to <body> as soon as it exists.
function applyThemePreferences() {
    const prefs = session.angels_theme;
    if (prefs) {
        document.body.classList.add(
            `o_at_density_${prefs.density}`,
            `o_at_tabs_${prefs.tab_style}`
        );
    }
}

if (document.body) {
    applyThemePreferences();
} else {
    document.addEventListener("DOMContentLoaded", applyThemePreferences);
}
