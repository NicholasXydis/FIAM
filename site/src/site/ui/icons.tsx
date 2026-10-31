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
  captions: (
    <>
      <rect width="18" height="14" x="3" y="5" rx="2" ry="2" />
      <path className="pill-accent" d="M7 15h4M15 15h2M7 11h2M13 11h4" />
    </>
  ),
  expand: (
    <>
      <path d="M8 3H5a2 2 0 0 0-2 2v3M16 21h3a2 2 0 0 0 2-2v-3" />
      <path className="pill-accent" d="M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3" />
    </>
  ),
  shrink: (
    <>
      <path d="M8 3v3a2 2 0 0 1-2 2H3M16 21v-3a2 2 0 0 1 2-2h3" />
      <path className="pill-accent" d="M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3" />
    </>
  ),
  home: (
    <>
      <path className="pill-accent" d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8" />
      <path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </>
  ),
  linkedin: (
    <>
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect width="4" height="12" x="2" y="9" />
      <circle className="pill-accent" cx="4" cy="4" r="2" />
    </>
  ),
  github: (
    <>
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path className="pill-accent" d="M9 18c-4.51 2-5-2-7-2" />
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
