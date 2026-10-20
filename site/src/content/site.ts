import { PEOPLE } from "./team";

// The words every site page frames itself with.
const FRAME = {
  name: "QUARCC Purple",
  event: "McGill-FIAM Asset Management Hackathon 2026 · Finals",
};

// Each page's words, sent to it as JSON so the browser needs no data.
export const CONTENT = {
  landing: {
    ...FRAME,
    project: "View the Project",
    team: "View the Team",
  },
  team: {
    ...FRAME,
    title: "The",
    gold: "Team",
    people: PEOPLE,
  },
  missing: {
    ...FRAME,
    title: "This page does not exist.",
    lead: "The address may be mistyped, or the page may have moved.",
    home: "Back to home",
  },
};

// The pages by name, each with the words it is given.
export type Content = typeof CONTENT;
