import type { Content } from "@/content/site";
import { Footer, Frame, Header } from "../ui/frame";
import { Pill } from "../ui/pill";

// Not found: one sentence and one way home; the name is not a link.
export function Missing({ name, event, title, lead, home }: Content["missing"]) {
  return (
    <Frame opening="dust" rows="grid-rows-[auto_1fr_auto]">
      <Header name={name} />
      <main className="flex flex-col items-center justify-center gap-flow text-center">
        <h1 className="animate-rise font-display text-title text-balance">{title}</h1>
        <p className="max-w-[34em] animate-rise text-lead text-pretty text-dim">{lead}</p>
        <Pill size="big" icon="home" label={home} href="/" className="animate-rise" />
      </main>
      <Footer event={event} />
    </Frame>
  );
}
