// What h() takes as a child; empty ones are skipped.
export type Child = Node | string | null | undefined | false;

// The one DOM builder; html sets innerHTML, false props are left out.
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Record<string, string | number | boolean> = {},
  ...children: Child[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "html") el.innerHTML = String(value);
    else if (value !== false) el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children) if (child) el.append(child);
  return el;
}
