import { useEffect, useRef } from "react";
import type { Content } from "@/content/site";
import { closePerson, slug, usePerson } from "../person";
import { goBack } from "../ui/back";
import { Footer, Frame, Header } from "../ui/frame";
import { Profile } from "../ui/profile";
import { Roster } from "../ui/roster";

// The team, or one person's section when the address names them.
export function Team({ name, event, title, gold, people }: Content["team"]) {
  const current = usePerson();
  const at = people.findIndex((p) => slug(p.name) === current);
  const person = people[at];
  const last = useRef<string | null>(null);
  // Focus and title follow the view: the name, then the circle on return.
  useEffect(() => {
    const was = last.current;
    last.current = person ? slug(person.name) : null;
    document.title = person ? `${person.name} · ${name}` : `${title} ${gold} · ${name}`;
    if (person && !was) document.getElementById("person-name")?.focus({ preventScroll: true });
    if (!person && was) document.querySelector<HTMLElement>(`[data-slug="${was}"]`)?.focus({ preventScroll: true });
  }, [person, name, title, gold]);
  // Each neighbour wraps round, so the last leads back to the first.
  const near = (step: number) => people[(at + step + people.length) % people.length]!;
  return (
    <Frame opening="dust" rows="grid-rows-[auto_1fr_auto]">
      <Header name={name} onBack={person ? closePerson : () => goBack()} />
      <main className="flex flex-col items-center justify-center gap-flow py-4 text-center">
        {person ? (
          <Profile person={person} before={near(-1)} after={near(1)} />
        ) : (
          <>
            <h1 className="animate-rise font-display text-title">
              {title} <em className="text-violet">{gold}</em>
            </h1>
            <Roster people={people} />
          </>
        )}
      </main>
      <Footer event={event} />
    </Frame>
  );
}
