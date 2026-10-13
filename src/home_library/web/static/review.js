// The review pages (review.js): keys for the keyboard, and "Use this record". Plain ES2020.
//
//   j / k      next / previous (focus moves between rows in the inbox; on a book, the page changes)
//   Enter      approve and go to the next; only when the person is not typing, so a text area keeps its Enter
//   Ctrl+Enter approve from anywhere, even inside a text area
//   e          edit: focus the title field
//   x          dismiss
//   Esc        leave a field, so the single keys work again
//
// While an input method is composing text, every key is left alone.
//
// The key rules are a plain function, exported for Node, where the tests run them.
(function () {
  "use strict";

  function keyAction(event, context) {
    // An input method (Japanese, Chinese) uses Esc to cancel a conversion and Enter to commit it; those keys are
    // not ours. Some browsers report the last keydown of a composition as keyCode 229 with isComposing already false.
    if (event.isComposing || event.keyCode === 229) return null;
    if (event.key === "Escape") return context.typing ? "blur" : null;
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) return "approve";
    if (event.ctrlKey || event.metaKey || event.altKey) return null;
    if (context.typing) return null; // a field keeps its own keys, Enter included
    if (event.key === "Enter") return context.onControl ? null : "approve"; // a focused button or link keeps Enter
    return { j: "next", k: "prev", e: "edit", x: "dismiss" }[event.key] || null;
  }

  // Which row gets focus: -1 means none yet; the ends stop rather than wrap.
  function moveFocus(index, count, direction) {
    if (count === 0) return -1;
    if (direction === "next") return Math.min(index + 1, count - 1);
    return index < 0 ? count - 1 : Math.max(index - 1, 0);
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { keyAction, moveFocus };
  if (typeof document === "undefined") return;

  function contextOf(target) {
    const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
    return {
      typing: tag === "input" || tag === "textarea" || tag === "select" || Boolean(target && target.isContentEditable),
      textarea: tag === "textarea",
      onControl: tag === "button" || tag === "a" || tag === "summary",
    };
  }

  function act(action) {
    const page = document.getElementById("review");
    const rows = Array.from(document.querySelectorAll("[data-row]"));
    if (action === "blur") {
      document.activeElement.blur();
    } else if (page) {
      const form = document.getElementById("approve-form");
      if (action === "next" && page.dataset.next) window.location.href = page.dataset.next;
      if (action === "prev" && page.dataset.prev) window.location.href = page.dataset.prev;
      if (action === "approve" && form && !form.classList.contains("htmx-request")) form.requestSubmit(document.getElementById("approve"));
      if (action === "edit") {
        const title = document.getElementById("f-title");
        if (title) { title.focus(); title.select(); }
      }
      if (action === "dismiss") {
        const button = document.getElementById("dismiss");
        if (button && !button.disabled) button.click();
      }
    } else if (rows.length && (action === "next" || action === "prev")) {
      const current = rows.indexOf(document.activeElement);
      rows[moveFocus(current, rows.length, action)].focus();
    }
  }

  document.addEventListener("keydown", function (event) {
    const action = keyAction(event, contextOf(event.target));
    if (action === null) return;
    event.preventDefault();
    act(action);
  });

  // "Use this record": copy the candidate's catalogue fields into the form, then let the person look and approve.
  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-fill]");
    if (!button) return;
    const fill = JSON.parse(button.dataset.fill);
    for (const key of Object.keys(fill)) {
      const field = document.getElementById("f-" + key);
      if (field) field.value = fill[key];
    }
    for (const other of document.querySelectorAll("[data-fill]")) other.removeAttribute("aria-pressed");
    button.setAttribute("aria-pressed", "true");
    const title = document.getElementById("f-title");
    if (title) title.focus();
  });
})();
