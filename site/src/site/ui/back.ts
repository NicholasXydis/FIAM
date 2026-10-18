// Back closes an open panel before leaving the page: one history step.

// The open panel's way to close, and a step back of ours not yet done.
let close: (() => void) | null = null;
let returning = false;
// A panel opened while our step back was still under way.
let queued: (() => void) | null = null;
let listening = false;

// Back pressed: undo our own step, or close the panel it was for.
function popped() {
  if (returning) {
    returning = false;
    queued?.();
    queued = null;
    return;
  }
  const shut = close;
  close = null;
  shut?.();
}

// A panel opened: add the history step that Back will spend on it.
export function opened(shut: () => void) {
  if (!listening) addEventListener("popstate", popped);
  listening = true;
  const push = () => {
    history.pushState({ panel: true }, "");
    close = shut;
  };
  if (returning) queued = push;
  else push();
}

// A panel closed by the page: take back the step it added.
export function closed() {
  if (queued) return void (queued = null);
  if (!close) return;
  close = null;
  returning = true;
  history.back();
}
