import type { CSSProperties } from "react";
import type { Person } from "@/content/team";
import { morph, openPerson, slug } from "../person";
import { afterPress, wire } from "./press";

// A person's initials, standing in until their photo is confirmed.
const initials = (name: string) =>
  name
    .split(" ")
    .map((w) => w[0])
    .join("");

// What sits in a face's circle: their photo, or their initials.
function Mark({ person }: { person: Person }) {
  return person.photo ? (
    <img src={person.photo} alt="" width={240} height={240} decoding="async" />
  ) : (
    <span className="face-mark">{initials(person.name)}</span>
  );
}

// A face: the circle with its mark, a ring that lights in, and ink.
export function Face({ person, big = false, inked = false }: { person: Person; big?: boolean; inked?: boolean }) {
  return (
    <span className={big ? "face face-big" : "face"} style={morph("face", person)}>
      <span className="face-disc" aria-hidden="true">
        <Mark person={person} />
      </span>
      {inked && (
        <span className="pill-ink" aria-hidden="true">
          {!person.photo && <Mark person={person} />}
        </span>
      )}
    </span>
  );
}

// A rise delay, shared with the ring so it lights as its person rises.
const enter = (s: number) => ({ animationDelay: `${s}s`, "--enter": `${s}s` }) as CSSProperties;

// The team: a circle and a name each, opening that person's section.
export function Roster({ people }: { people: Person[] }) {
  return (
    <ul className="roster">
      {people.map((p, i) => (
        <li key={p.name} className="animate-rise" style={enter(0.12 + i * 0.07)}>
          <button
            ref={wire}
            type="button"
            className="person"
            data-slug={slug(p.name)}
            onClick={() => afterPress(() => openPerson(slug(p.name)))}
          >
            <Face person={p} inked />
            <span className="person-name" style={morph("name", p)}>
              {p.name}
            </span>
            {p.role && <span className="person-role">{p.role}</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
