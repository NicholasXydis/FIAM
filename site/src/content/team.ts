// One person; a role, photo or link shows only once it is confirmed.
export interface Person {
  name: string;
  role?: string;
  photo?: string;
  linkedin?: string;
}

// The team in page order; add each detail once the person confirms it.
export const PEOPLE: Person[] = [
  { name: "Nicholas Xydis" },
  { name: "Yohannah Ilieva" },
  { name: "Andrew Koumoudjian" },
  { name: "Nicolas Romero" },
  { name: "Nokto Lapointe" },
];
