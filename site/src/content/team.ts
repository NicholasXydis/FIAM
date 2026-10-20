// One person; every detail but the name shows once they confirm it.
export interface Person {
  name: string;
  role?: string;
  photo?: string;
  linkedin?: string;
  about?: string;
  focus?: string[];
}

// The team in page order; add each detail once the person confirms it.
export const PEOPLE: Person[] = [
  { name: "Nicholas Xydis", photo: "/people/nicholas-xydis.webp" },
  { name: "Yohannah Ilieva", photo: "/people/yohannah-ilieva.webp" },
  { name: "Andrew Koumoudjian", photo: "/people/andrew-koumoudjian.webp" },
  { name: "Nicolas Romero", photo: "/people/nicolas-romero.webp" },
  { name: "Nokto Lapointe" },
];
