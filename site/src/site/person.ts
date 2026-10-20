import { type CSSProperties, useLayoutEffect, useState } from "react";
import { flushSync } from "react-dom";

// A person's address after #, from their name.
export const slug = (name: string) => name.toLowerCase().replace(/\s+/g, "-");

// A view-transition name, so a face or name morphs between views.
export const morph = (kind: string, person: { name: string }) =>
  ({ viewTransitionName: `${kind}-${slug(person.name)}` }) as CSSProperties;

// Swaps the view in a view transition, unless motion is reduced.
function transition(change: () => void) {
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || still) return change();
  // A transition cut short by the next one is fine; keep it quiet.
  const swap = document.startViewTransition(() => flushSync(change));
  swap.ready.catch(() => undefined);
  swap.finished.catch(() => undefined);
}

// The person the address names; a malformed one names nobody.
const read = () => {
  try {
    return decodeURIComponent(location.hash.slice(1));
  } catch {
    return "";
  }
};

// The person the address names after #, kept in step with Back.
export function usePerson() {
  const [current, setCurrent] = useState("");
  // Read before first paint, so a link to a person never shows the list.
  useLayoutEffect(() => {
    setCurrent(read());
    document.documentElement.removeAttribute("data-person");
    const change = () => transition(() => setCurrent(read()));
    addEventListener("hashchange", change);
    return () => removeEventListener("hashchange", change);
  }, []);
  return current;
}

// Opens a person; a step to a neighbour replaces it, so Back skips it.
export function openPerson(to: string, step = false) {
  const kept: unknown = history.state;
  if (step) location.replace(`#${to}`);
  else location.hash = to;
  // The entry remembers it was opened from the list, even after a reload.
  history.replaceState(step ? kept : { opened: true }, "");
}

// Back from a person: undo the open, or go up to the list.
export function closePerson() {
  if ((history.state as { opened?: boolean } | null)?.opened) return history.back();
  history.replaceState(null, "", location.pathname);
  dispatchEvent(new HashChangeEvent("hashchange"));
}
