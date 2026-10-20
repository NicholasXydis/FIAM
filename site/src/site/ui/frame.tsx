import type { ReactNode } from "react";
import { Pill } from "./pill";
import { type Opening, Sky } from "./sky";

// The top of an inner page: Back, and the name, which is not a link.
export function Header({ name, onBack }: { name: string; onBack?: () => void }) {
  const [first, ...rest] = name.split(" ");
  return (
    <header className="flex min-h-touch items-center justify-between gap-4 [view-transition-name:header]">
      {onBack ? <Pill label="Back" icon="left" href="/" onPress={onBack} /> : <span />}
      <p className="font-display text-brand">
        {first} <em className="text-violet">{rest.join(" ")}</em>
      </p>
    </header>
  );
}

// The foot of every page: the event, at the bottom left.
export function Footer({ event }: { event: string }) {
  return (
    <footer className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1 font-mono text-foot tracking-[0.16em] text-dim/75 uppercase">
      <span>{event}</span>
    </footer>
  );
}

// Every page: the night behind, then a grid clear of notches.
export function Frame({ opening, rows, children }: { opening: Opening; rows: string; children: ReactNode }) {
  return (
    <>
      <Sky opening={opening} />
      <div className={`relative grid min-h-svh gap-flow safe ${rows}`}>{children}</div>
    </>
  );
}
