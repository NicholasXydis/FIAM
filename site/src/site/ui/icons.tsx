// Lucide icons (ISC licence, lucide.dev); the accent part pops in.
const ICONS = {
  play: (
    <>
      <circle cx="12" cy="12" r="10" />
      <polygon className="pill-accent" points="10 8 16 12 10 16 10 8" />
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <g className="pill-accent">
        <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </g>
    </>
  ),
  left: (
    <>
      <path className="pill-accent" d="m12 19-7-7 7-7" />
      <path d="M19 12H5" />
    </>
  ),
  right: (
    <>
      <path d="M5 12h14" />
      <path className="pill-accent" d="m12 5 7 7-7 7" />
    </>
  ),
  out: (
    <>
      <path className="pill-accent" d="M7 7h10v10" />
      <path d="M7 17 17 7" />
    </>
  ),
  home: (
    <>
      <path className="pill-accent" d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" />
      <path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </>
  ),
};

// The icons a pill can carry, by name.
export type IconName = keyof typeof ICONS;

// One icon in the words' colour, so the ink inverts it with them.
export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="pill-icon" viewBox="0 0 24 24" aria-hidden="true">
      {ICONS[name]}
    </svg>
  );
}
