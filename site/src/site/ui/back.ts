// The page of this site the visitor came from, or null from outside.
export function cameFrom() {
  // A blank referrer throws, which counts as coming from outside.
  try {
    const from = new URL(document.referrer);
    return from.origin === location.origin ? from.pathname : null;
  } catch {
    return null;
  }
}

// Back steps to the page before when it was on this site, else home.
export function goBack() {
  if (cameFrom() !== null && history.length > 1) history.back();
  else location.assign("/");
}
