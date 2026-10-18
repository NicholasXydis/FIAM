import type { ReactNode } from "react";

// The film's wide-tracked line above a title, in mono capitals.
export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="font-mono text-eyebrow text-balance text-dim uppercase">{children}</p>;
}
