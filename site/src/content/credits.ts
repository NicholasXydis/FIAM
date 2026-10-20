import { PEOPLE } from "./team.ts";

// The finale's QR link: the project's source code on GitHub.
export const QR_TEXT = "https://github.com/NicholasXydis/FIAM";

// The team's names in page order, for the tour's and film's credits.
export const TEAM = PEOPLE.map((p) => p.name);
