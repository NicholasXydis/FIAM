import type { Content } from "@/content/site";
import { Footer, Frame } from "../ui/frame";
import { Pill } from "../ui/pill";

// The name in light, two ways in, and the event at the foot.
export function Landing({ name, event, project, team }: Content["landing"]) {
  const [first, ...rest] = name.split(" ");
  return (
    <Frame opening="name" rows="grid-rows-[1fr_auto_auto]">
      <main data-stage className="grid min-h-0 place-items-center">
        <h1 className="wordmark">
          <span>{first}</span> <em>{rest.join(" ")}</em>
        </h1>
      </main>
      <nav aria-label="Ways in" className="ways">
        <Pill size="big" icon="play" label={project} href="/tour/" />
        <Pill size="big" icon="users" label={team} href="/team/" />
      </nav>
      <Footer event={event} />
    </Frame>
  );
}
