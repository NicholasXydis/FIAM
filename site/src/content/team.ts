// One person; every detail but the name shows once they confirm it.
export interface Person {
  name: string;
  role?: string;
  photo?: string;
  linkedin?: string;
  github?: string;
  about?: string;
  focus?: string[];
}

// Members in page order; each detail is added once confirmed.
export const PEOPLE: Person[] = [
  {
    name: "Nicholas Xydis",
    role: "AI & Research",
    photo: "/people/nicholas-xydis.webp",
    linkedin: "https://www.linkedin.com/in/nicholasxydis/",
    github: "https://github.com/NicholasXydis",
  },
  {
    name: "Yohannah Ilieva",
    role: "Risk Management",
    photo: "/people/yohannah-ilieva.webp",
    linkedin: "https://www.linkedin.com/in/yohannahilieva/",
  },
  {
    name: "Andrew Koumoudjian",
    role: "Portfolio Construction",
    photo: "/people/andrew-koumoudjian.webp",
    linkedin: "https://www.linkedin.com/in/andrewkoumoudjian/",
  },
  {
    name: "Nicolas Romero",
    role: "Data & Finance",
    photo: "/people/nicolas-romero.webp",
    linkedin: "https://www.linkedin.com/in/nicolasdavidromero/",
  },
  { name: "Nokto Lapointe", role: "Machine Learning", photo: "/people/nokto-lapointe.webp" },
];
