import { m } from "motion/react";
import { type CSSProperties, useEffect, useState } from "react";
import { PRESS } from "../motion/presets";
import { closed, opened } from "./back";

// One figure as it reads on the page, and what it means.
export interface Figure {
  label: string;
  text: string;
}

// The book's figures, each opening its meaning; Back closes it first.
export function Figures({ items }: { items: Figure[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const active = open !== null;
  // One history step while any figure is open, spent by Back.
  useEffect(() => {
    if (!active) return;
    opened(() => document.querySelector<HTMLElement>(".definition:popover-open")?.hidePopover());
    return closed;
  }, [active]);
  return (
    <>
      <ul
        aria-label="The book in three figures"
        className="mt-[calc(var(--spacing-flow)*0.2)] flex flex-col items-center @min-[40rem]:flex-row @min-[40rem]:flex-wrap @min-[40rem]:justify-center @min-[40rem]:gap-x-[calc(var(--spacing-flow)*1.2)]"
      >
        {items.map((f, i) => (
          <li key={f.label} style={{ anchorName: `--figure-${i}` } as CSSProperties}>
            <m.button
              type="button"
              popoverTarget={`figure-${i}`}
              {...PRESS}
              className="min-h-touch cursor-pointer rounded-md px-[0.15em] text-body text-moon tabular-nums underline decoration-moon/50 decoration-dotted underline-offset-[0.3em] hover:decoration-solid"
            >
              {f.label}
            </m.button>
          </li>
        ))}
      </ul>
      {items.map((f, i) => (
        <div
          key={f.label}
          id={`figure-${i}`}
          popover="auto"
          onToggle={(e) => {
            const now = e.newState === "open";
            setOpen((was) => (now ? i : was === i ? null : was));
          }}
          style={{ positionAnchor: `--figure-${i}` } as CSSProperties}
          className="definition"
        >
          <p className="mb-1.5 font-medium text-gold">{f.label}</p>
          <p>{f.text}</p>
        </div>
      ))}
    </>
  );
}
