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
