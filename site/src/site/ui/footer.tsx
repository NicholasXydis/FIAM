// The backtest's disclaimer, small, at the foot of every page.
export function Footer({ disclaimer }: { disclaimer: string }) {
  return (
    <footer className="pt-flow safe-bottom text-center text-small text-dim/85">
      <p className="mx-auto max-w-[46em] text-balance">{disclaimer}</p>
    </footer>
  );
}
