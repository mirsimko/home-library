// The capture page (capture.js). Plain ES2020, no framework, no network except the app's own JSON API.
//
// Every chosen photo gets its capture id at once. It is uploaded on its own with XMLHttpRequest (for the
// progress bar) and, while the page stays open, retried up to five times with growing waits. The server
// is idempotent for a repeated id, so a retry is always safe. Statuses come from polling
// GET /api/captures?ids= every 10 seconds until a photo is in a final state.
//
// The logic that does not touch the page is kept apart and exported for Node, where the tests run it.
(function () {
  "use strict";

  const RETRY_DELAYS = [2, 4, 8, 16, 32]; // seconds before each retry
  const POLL_SECONDS = 10;
  const SMALL_SIDE = 3000; // a camera original is longer than this; a smaller photo was shrunk on the way
  const FINAL = ["needs attention", "ready for review"];

  function newId() {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    // Older browsers outside a secure context have no randomUUID; make a version 4 id by hand.
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
  }

  // ---- what a photo's status says -------------------------------------------------------------

  function statusOf(item) {
    if (item.state === "failed" || item.state === "rejected") return "needs attention";
    if (item.state !== "uploaded") return "on this phone";
    const job = item.job ? item.job.status : "queued";
    if (job === "running") return "reading";
    if (job === "failed") return "needs attention";
    if (job === "done") return item.open_observations > 0 ? "ready for review" : "needs attention";
    return "received";
  }

  function isFinal(item) {
    return FINAL.includes(statusOf(item));
  }

  // The phase 0 capture test: the camera's original is well over 3000 px on its long side.
  function isSmall(width, height) {
    return Math.max(width, height) < SMALL_SIDE;
  }

  // ---- what each photo is: shelf, cover or barcode ----------------------------------------------

  function startFlow(mode) {
    return { mode: mode, step: "cover", groupId: null };
  }

  // Decide the kind and group of the next photo, and where the walk-through stands afterwards.
  function assign(flow, makeId) {
    if (flow.mode === "shelf") return { kind: "shelf", group_id: null, flow: flow };
    if (flow.step === "barcode" && flow.groupId) {
      return { kind: "barcode", group_id: flow.groupId, flow: { mode: "book", step: "cover", groupId: null } };
    }
    const group = makeId();
    return { kind: "cover", group_id: group, flow: { mode: "book", step: "after-cover", groupId: group } };
  }

  function askBarcode(flow) {
    return flow.groupId ? { mode: "book", step: "barcode", groupId: flow.groupId } : flow;
  }

  function nextBook(flow) {
    return startFlow(flow.mode);
  }

  function prompt(flow) {
    if (flow.mode === "shelf") return "Photograph a shelf. Take as many as you like; each is sent on its own.";
    if (flow.step === "after-cover") return "Cover saved. Add its barcode photo, or go on to the next book.";
    if (flow.step === "barcode") return "Photograph the barcode on the back of the same book.";
    return "Photograph the front cover of one book.";
  }

  // ---- sending, one photo at a time ---------------------------------------------------------------

  function retryDelay(failures) {
    return failures >= 1 && failures <= RETRY_DELAYS.length ? RETRY_DELAYS[failures - 1] : null;
  }

  // No connection (0), a timeout, a busy server or a server fault may pass; the photo itself being refused will not.
  function isRetryable(status) {
    return status === 0 || status === 408 || status === 429 || status >= 500;
  }

  // The queue: `send(item, done)` does one upload and calls done({ok, receipt} or {ok:false, status, message});
  // `schedule(run, seconds)` waits; `changed(item)` redraws. A photo waiting to retry steps aside so that the
  // others are not held up behind it.
  function createUploader(options) {
    const queue = [];
    let busy = false;

    function pump() {
      if (busy) return;
      const item = queue.find((candidate) => candidate.state === "waiting");
      if (!item) return;
      busy = true;
      item.state = "sending";
      item.progress = 0;
      options.changed(item);
      options.send(item, (result) => {
        busy = false;
        if (result.ok) {
          item.state = "uploaded";
          item.receipt = result.receipt;
        } else if (isRetryable(result.status)) {
          item.failures += 1;
          item.message = result.message;
          const delay = retryDelay(item.failures);
          if (delay === null) {
            item.state = "failed";
          } else {
            item.state = "backoff";
            item.retryIn = delay;
            options.schedule(() => {
              if (item.state === "backoff") {
                item.state = "waiting";
                pump();
              }
            }, delay);
          }
        } else {
          item.state = "rejected";
          item.message = result.message;
        }
        options.changed(item);
        pump();
      });
    }

    return {
      add(item) {
        item.state = "waiting";
        item.failures = 0;
        queue.push(item);
        options.changed(item);
        pump();
      },
      retry(item) {
        item.failures = 0;
        item.state = "waiting";
        options.changed(item);
        pump();
      },
    };
  }

  const logic = {
    RETRY_DELAYS, statusOf, isFinal, isSmall, startFlow, assign, askBarcode, nextBook, prompt,
    retryDelay, isRetryable, createUploader,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = logic;
  if (typeof document === "undefined") return;

  // ---- the page -----------------------------------------------------------------------------------

  function remembered(key) {
    try { return localStorage.getItem(key); } catch (error) { return null; }
  }

  function remember(key, value) {
    try { localStorage.setItem(key, value); } catch (error) { /* private mode: nothing to remember */ }
  }

  function sendWithXhr(item, done) {
    const form = new FormData();
    form.append("id", item.id);
    form.append("kind", item.kind);
    form.append("location_id", item.location_id);
    form.append("state", item.default_state);
    if (item.group_id) form.append("group_id", item.group_id);
    form.append("file", item.file, item.file.name);
    const request = new XMLHttpRequest();
    request.open("POST", "/api/captures");
    request.timeout = 5 * 60 * 1000;
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        item.progress = Math.round((100 * event.loaded) / event.total);
        draw(item);
      }
    };
    request.onload = () => {
      let body = null;
      try { body = JSON.parse(request.responseText); } catch (error) { body = null; }
      if (request.status === 200 || request.status === 201) {
        done({ ok: true, receipt: body });
      } else {
        done({ ok: false, status: request.status, message: (body && body.error) || "The server refused this photo." });
      }
    };
    request.onerror = () => done({ ok: false, status: 0, message: "No connection." });
    request.ontimeout = () => done({ ok: false, status: 408, message: "The upload took too long." });
    request.send(form);
  }

  const items = [];
  let uploader = null;
  let flow = startFlow("shelf");
  const KIND_LABELS = { shelf: "Shelf", cover: "Cover", barcode: "Barcode" };

  function draw(item) {
    if (!item.element) {
      const li = document.createElement("li");
      li.className = "photo";
      li.innerHTML = '<img alt=""><div><div class="top"><span class="badge"></span><span class="small muted"></span></div>' +
        '<div class="detail"></div><div class="detail warn" hidden></div><progress max="100" hidden></progress>' +
        '<button type="button" hidden>Try again</button></div>';
      li.querySelector("img").src = item.thumbnail;
      li.querySelector("button").addEventListener("click", () => uploader.retry(item));
      item.element = li;
      document.getElementById("photos").prepend(li);
    }
    const li = item.element;
    const label = statusOf(item);
    const badge = li.querySelector(".badge");
    badge.textContent = label;
    badge.className = "badge" + (label === "ready for review" ? " good" : label === "needs attention" ? " bad" : "");
    li.querySelector(".top .small").textContent = KIND_LABELS[item.kind];
    const [detail, warning] = li.querySelectorAll(".detail");
    const progress = li.querySelector("progress");
    progress.hidden = item.state !== "sending";
    progress.value = item.progress || 0;
    li.querySelector("button").hidden = !(item.state === "failed" || item.state === "rejected");
    detail.textContent = detailText(item);
    const image = item.receipt && item.receipt.image;
    warning.hidden = !(image && isSmall(image.width, image.height));
    warning.textContent = warning.hidden ? "" : "This photo is smaller than the camera's original; check the camera settings.";
  }

  function detailText(item) {
    if (item.state === "waiting") return "Waiting to be sent";
    if (item.state === "sending") return "Sending… " + (item.progress || 0) + "%";
    if (item.state === "backoff") return "Could not be sent. Trying again in " + item.retryIn + " seconds (retry " + item.failures + " of 5).";
    if (item.state === "failed") return "Could not be sent after 5 retries. Check the connection, then try again.";
    if (item.state === "rejected") return item.message;
    const image = item.receipt && item.receipt.image;
    let text = "Received" + (image ? " · " + image.width + " × " + image.height + " px" : "");
    if (item.receipt && item.receipt.duplicate_of) text += " · the same picture was sent before";
    const label = statusOf(item);
    if (label === "reading") text += " · reading it now";
    if (label === "ready for review") text += " · " + item.open_observations + " to review";
    if (label === "needs attention") text += item.job && item.job.status === "failed" ? " · reading failed, see Status" : " · nothing was found in it, see Status";
    return text;
  }

  async function poll() {
    const ids = items.filter((item) => item.state === "uploaded" && !isFinal(item)).map((item) => item.id);
    if (!ids.length) return;
    try {
      const response = await fetch("/api/captures?ids=" + ids.join(","), { credentials: "same-origin" });
      if (!response.ok) return;
      for (const entry of await response.json()) {
        const item = items.find((candidate) => candidate.id === entry.capture.id);
        if (!item) continue;
        item.job = entry.job;
        item.open_observations = entry.open_observations;
        draw(item);
      }
    } catch (error) { /* offline for a moment; the next poll tries again */ }
  }

  function addFiles(files) {
    const location = document.getElementById("location").value;
    const state = document.getElementById("state").value;
    for (const file of files) {
      const plan = assign(flow, newId);
      flow = plan.flow;
      const item = {
        id: newId(), file: file, kind: plan.kind, group_id: plan.group_id, location_id: location,
        default_state: state, thumbnail: URL.createObjectURL(file), progress: 0, job: null, open_observations: 0,
      };
      items.push(item);
      uploader.add(item);
    }
    document.getElementById("stay-note").hidden = false;
    showFlow();
  }

  function showFlow() {
    document.getElementById("prompt").textContent = prompt(flow);
    // Still shown while a barcode is awaited, so that "Next book" can skip it.
    document.getElementById("book-step").hidden = !(flow.mode === "book" && flow.step !== "cover");
    for (const button of document.querySelectorAll("[data-mode]")) {
      button.setAttribute("aria-pressed", String(button.dataset.mode === flow.mode));
    }
  }

  function init() {
    uploader = createUploader({
      send: sendWithXhr,
      schedule: (run, seconds) => setTimeout(run, seconds * 1000),
      changed: draw,
    });
    const location = document.getElementById("location");
    const state = document.getElementById("state");
    for (const [select, key] of [[location, "hl.location"], [state, "hl.state"]]) {
      const saved = remembered(key);
      if (saved && Array.from(select.options).some((option) => option.value === saved)) select.value = saved;
      select.addEventListener("change", () => remember(key, select.value));
    }
    flow = startFlow(remembered("hl.mode") === "book" ? "book" : "shelf");
    for (const button of document.querySelectorAll("[data-mode]")) {
      button.addEventListener("click", () => {
        flow = startFlow(button.dataset.mode);
        remember("hl.mode", flow.mode);
        showFlow();
      });
    }
    for (const input of [document.getElementById("camera"), document.getElementById("gallery")]) {
      input.addEventListener("change", () => {
        addFiles(Array.from(input.files));
        input.value = ""; // choosing the same file again must still fire a change
      });
    }
    document.getElementById("add-barcode").addEventListener("click", () => {
      flow = askBarcode(flow);
      showFlow();
      document.getElementById("camera").click();
    });
    document.getElementById("next-book").addEventListener("click", () => {
      flow = nextBook(flow);
      showFlow();
    });
    window.addEventListener("beforeunload", (event) => {
      if (items.some((item) => ["waiting", "sending", "backoff"].includes(item.state))) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
    setInterval(poll, POLL_SECONDS * 1000);
    showFlow();
  }

  init();
})();
