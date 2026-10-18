import type { ReactNode } from "react";

// The sentence under a title, dimmed and kept to a readable measure.
export function Lead({ children }: { children: ReactNode }) {
  return <p className="max-w-[34em] text-lead text-pretty text-dim">{children}</p>;
}
