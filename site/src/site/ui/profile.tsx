import { useEffect } from "react";
import type { Person } from "@/content/team";
import { closePerson, morph, openPerson, slug } from "../person";
import { Pill } from "./pill";
import { Face } from "./roster";

// One person's section, its neighbours, and what to say until it fills.
interface Props {
  person: Person;
  before: Person;
  after: Person;
}

// A person: their face, name, role and paragraph, as each is confirmed.
export function Profile({ person, before, after }: Props) {
  const [first, ...rest] = person.name.split(" ");
  // Bare arrow keys step to a neighbour; Escape goes back to the list.
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.repeat) return;
      if (e.key === "ArrowRight") openPerson(slug(after.name), true);
      if (e.key === "ArrowLeft") openPerson(slug(before.name), true);
      if (e.key === "Escape") closePerson();
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, [before, after]);
  return (
    <div className="flex w-full flex-col items-center gap-flow">
      <section className="profile" aria-labelledby="person-name">
        <Face person={person} big />
        <div className="profile-info">
          {person.role && <p className="profile-role">{person.role}</p>}
          <h1 id="person-name" tabIndex={-1} className="profile-name" style={morph("name", person)}>
            {first} <em>{rest.join(" ")}</em>
          </h1>
          <div className="profile-rule" aria-hidden="true" />
          {person.about && <p className="profile-about">{person.about}</p>}
          {person.focus && (
            <ul className="profile-focus">
              {person.focus.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
          {person.linkedin && <Pill label="LinkedIn" icon="out" trailing external href={person.linkedin} />}
        </div>
      </section>
      <nav aria-label="Other people" className="grid w-full max-w-120 grid-cols-2 gap-3 max-[34rem]:grid-cols-1">
        <Pill label={before.name} caption="Previous" icon="left" onPress={() => openPerson(slug(before.name), true)} />
        <Pill
          label={after.name}
          caption="Next"
          icon="right"
          trailing
          onPress={() => openPerson(slug(after.name), true)}
        />
      </nav>
    </div>
  );
}
