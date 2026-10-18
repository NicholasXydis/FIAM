// The page a header sits on, so it can mark where the visitor is.
export type Here = "landing" | "team" | "missing";

// A page link in the header, marked current where the visitor is.
function Link({ href, here, children }: { href: string; here: boolean; children: string }) {
  return (
    <a
      href={href}
      aria-current={here ? "page" : undefined}
      className="inline-flex min-h-touch items-center rounded-full px-[0.95em] text-body text-dim no-underline transition-colors hover:bg-glass hover:text-moon aria-[current=page]:text-moon aria-[current=page]:shadow-[inset_0_0_0_1px_var(--color-hairline)]"
    >
      {children}
    </a>
  );
}

// The mark linking home, then Tour and Team; the landing has no nav.
export function Header({ name, here }: { name: string; here: Here }) {
  return (
    <header className="flex items-center justify-between gap-flow safe-top [view-transition-name:bar]">
      <a
        href="/"
        className="brand inline-flex min-h-touch items-center gap-[0.6em] font-display text-lead no-underline"
      >
        <img src="/favicon.svg" width={28} height={28} alt="" className="size-[1.35em] rounded-[0.3em]" />
        <span>{name}</span>
      </a>
      {here !== "landing" && (
        <nav aria-label="Main" className="flex gap-1">
          <Link href="/tour/" here={false}>
            Tour
          </Link>
          <Link href="/team/" here={here === "team"}>
            Team
          </Link>
        </nav>
      )}
    </header>
  );
}
