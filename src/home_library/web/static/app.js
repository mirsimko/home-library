// Small behaviours every page shares: the install-only service worker, and HTMX showing error fragments.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(function () {});
}

// HTMX does not swap 4xx answers by default. The pages answer a refused action with a status and a short
// message fragment, so let those through and let the target show them.
document.addEventListener("htmx:beforeSwap", function (event) {
  const status = event.detail.xhr.status;
  if (status === 400 || status === 404 || status === 409) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});

// The selection bar on the books page: count the ticked books and enable "Apply" only when there are some.
function updateSelection() {
  const form = document.getElementById("bulk");
  if (!form) return;
  const boxes = Array.from(form.querySelectorAll('input[name="book_ids"]'));
  const picked = boxes.filter((box) => box.checked);
  form.querySelector("[data-selected-count]").textContent = picked.length + " selected";
  form.querySelector("[data-apply]").disabled = picked.length === 0;
  const all = form.querySelector("[data-select-all]");
  all.checked = boxes.length > 0 && picked.length === boxes.length;
  for (const box of boxes) box.closest("tr").classList.toggle("pick", box.checked);
}

document.addEventListener("change", function (event) {
  if (event.target.matches("[data-select-all]")) {
    for (const box of document.querySelectorAll('#bulk input[name="book_ids"]')) box.checked = event.target.checked;
  }
  if (event.target.matches("#bulk input")) updateSelection();
});
document.addEventListener("htmx:afterSettle", updateSelection);
