import { PEOPLE } from "./team.ts";

// The finale's QR text; the team and event until there is a link.
export const QR_TEXT = "QUARCC Purple · FIAM · McGill-FIAM Asset Management Hackathon 2026 Finals";

// The team's names in page order, for the tour's and film's credits.
export const TEAM = PEOPLE.map((p) => p.name);
