import type { Person } from "@/content/team";
import { Reveal } from "../motion/reveal";

// A person's initials, standing in until a photo is confirmed.
const initials = (name: string) =>
  name
    .split(" ")
    .map((w) => w[0])
    .join("");

// One person: photo or initials, the name, and confirmed details only.
function Member({ name, role, photo, linkedin }: Person) {
  return (
    <>
      {photo ? (
        <img
          src={photo}
          width={112}
          height={112}
          alt=""
          loading="lazy"
          decoding="async"
          className="face object-cover"
        />
      ) : (
        <span aria-hidden="true" className="grid face place-items-center font-display text-moon">
          {initials(name)}
        </span>
      )}
      <div className="flex flex-col items-center gap-0.5 @max-[30rem]:items-start">
        <p className="font-display text-[calc(var(--text-lead)*1.25)] leading-[1.1]">{name}</p>
        {role && <p className="text-small text-dim">{role}</p>}
        {linkedin && (
          <a
            href={linkedin}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${name} on LinkedIn`}
            className="inline-flex min-h-touch items-center text-small underline-offset-[0.25em]"
          >
            LinkedIn
          </a>
        )}
      </div>
    </>
  );
}

// The team: five across, else three and two, else one to a row.
export function Roster({ people }: { people: Person[] }) {
  return (
    <ul className="@container mt-flow flex w-full flex-wrap justify-center gap-x-flow gap-y-[calc(var(--spacing-flow)*1.4)]">
      {people.map((p, i) => (
        <Reveal
          as="li"
          key={p.name}
          order={i}
          className="flex shrink-0 grow-0 basis-[calc((100%_-_2*var(--spacing-flow))/3)] flex-col items-center gap-3 @max-[30rem]:basis-full @max-[30rem]:flex-row @max-[30rem]:gap-4 @max-[30rem]:text-left @min-[62rem]:basis-[calc((100%_-_4*var(--spacing-flow))/5)]"
        >
          <Member {...p} />
        </Reveal>
      ))}
    </ul>
  );
}
