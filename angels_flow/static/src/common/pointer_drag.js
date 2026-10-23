/**
 * Drag with pointer events, as the Angels Sign editor does: it works with a
 * mouse, a pen or a finger, unlike native HTML5 drag and drop.
 *
 * Below a few pixels of movement the gesture is a click. While dragging, an
 * optional label follows the pointer; Escape cancels.
 */
const THRESHOLD = 4;

export function startPointerDrag(ev, { label, immediate, cursor, onMove, onDrop, onClick, onCancel }) {
    if (ev.pointerType === "mouse" && ev.button !== 0) {
        return;
    }
    ev.preventDefault();
    const start = { x: ev.clientX, y: ev.clientY };
    let dragging = false;
    let ghost = null;

    const begin = () => {
        dragging = true;
        if (label) {
            ghost = document.createElement("div");
            ghost.className = "o_af_ghost";
            ghost.textContent = label;
            document.body.appendChild(ghost);
        }
        if (cursor) {
            document.body.style.cursor = cursor;
        }
    };
    const stop = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", cancel);
        window.removeEventListener("keydown", key, true);
        ghost?.remove();
        document.body.style.cursor = "";
    };
    const move = (moveEv) => {
        if (!dragging && Math.hypot(moveEv.clientX - start.x, moveEv.clientY - start.y) > THRESHOLD) {
            begin();
        }
        if (dragging) {
            if (ghost) {
                ghost.style.left = `${moveEv.clientX + 10}px`;
                ghost.style.top = `${moveEv.clientY + 10}px`;
            }
            onMove?.(moveEv.clientX, moveEv.clientY);
        }
    };
    const up = (upEv) => {
        stop();
        if (dragging) {
            onDrop?.(upEv.clientX, upEv.clientY);
        } else {
            onClick?.();
        }
    };
    const cancel = () => {
        stop();
        onCancel?.();
    };
    const key = (keyEv) => {
        if (keyEv.key === "Escape") {
            keyEv.stopPropagation();
            cancel();
        }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
    if (immediate) {
        begin();
    }
}
