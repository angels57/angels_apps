/**
 * Questions sit on a 12-column grid: a row number, a start column and a width.
 * Older questions all have row 0 and column 0: they simply follow each other
 * and wrap, as they did before the grid existed.
 */

// Columns of each width (angels.form.field.width).
export const WIDTH_COLS = { quarter: 3, third: 4, half: 6, two_thirds: 8, three_quarters: 9, full: 12 };
export const COLUMNS = 12;

export function spanOf(field) {
    return field.type === "section" ? COLUMNS : WIDTH_COLS[field.width] || COLUMNS;
}

/** Widest allowed width that fits in ``free`` columns, or false. */
export function widthFitting(free) {
    const fits = Object.entries(WIDTH_COLS).filter(([, cols]) => cols <= free);
    return fits.length ? fits.reduce((a, b) => (b[1] > a[1] ? b : a))[0] : false;
}

/** Reading order: by row, then column (stable, so older questions keep their order). */
export function byPlace(fields) {
    return [...fields].sort((a, b) => (a.row || 0) - (b.row || 0) || (a.col || 0) - (b.col || 0));
}

/**
 * How the fill screen lays out ``fields``: a line break before each new row,
 * and an offset where a question starts after a gap.
 */
export function layoutItems(fields) {
    const items = [];
    let row = null;
    let cursor = 0;
    for (const field of byPlace(fields)) {
        const span = spanOf(field);
        const newRow = row !== null && (field.row || 0) !== row;
        if (row === null || newRow) {
            cursor = 0;
        }
        row = field.row || 0;
        let offset = Math.max(0, (field.col || 0) - cursor);
        if (cursor + offset + span > COLUMNS) {
            offset = 0;
        }
        items.push({ field, offset, breakBefore: newRow });
        let end = cursor + offset + span;
        if (end > COLUMNS) {
            end = span; // wraps onto a new line
        }
        cursor = end >= COLUMNS ? 0 : end;
    }
    return items;
}

/** True when two questions of a row overlap or one overflows: the grid must be rebuilt. */
export function needsPacking(fields) {
    const rows = new Map();
    for (const field of fields) {
        const cells = rows.get(field.row || 0) || new Set();
        const start = field.col || 0;
        const span = spanOf(field);
        if (start + span > COLUMNS) {
            return true;
        }
        for (let col = start; col < start + span; col++) {
            if (cells.has(col)) {
                return true;
            }
            cells.add(col);
        }
        rows.set(field.row || 0, cells);
    }
    return false;
}

/** Give each question a row and a column, following their current order (in place). */
export function packLayout(fields) {
    let row = 0;
    let col = 0;
    for (const field of fields) {
        const span = spanOf(field);
        if (col > 0 && (col + span > COLUMNS || field.type === "section")) {
            row++;
            col = 0;
        }
        field.row = row;
        field.col = col;
        col += span;
        if (col >= COLUMNS) {
            row++;
            col = 0;
        }
    }
}

/** Renumber rows 0, 1, 2... without gaps (in place). */
export function compactRows(fields) {
    const rows = [...new Set(fields.map((f) => f.row || 0))].sort((a, b) => a - b);
    const index = new Map(rows.map((row, i) => [row, i]));
    for (const field of fields) {
        field.row = index.get(field.row || 0);
    }
}
