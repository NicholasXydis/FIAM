import crashes from "../data/crashes.json";
import { agents, headline, journey, signals } from "../data/fiam.json";
import film from "./data.json";

// The approved film's agents and crowd from data.json, then the desk.
export const ROLES = [...film.original.roles, agents.find((a) => a.key === "desk")!.name];
export const INVESTORS = film.original.crowd.agents + film.original.crowd.copycats;
// The updates from the final fund: beta, signals and stocks a month.
export const BETA = headline.beta;
export const SIGNALS = signals.length;
export const STOCKS = Math.round(journey.average / 100) * 100;
// The final book's replayed crises, for the sea's ripples and marks.
export const CRASHES = crashes;
// The final fund's yearly volatility in percent, table row 4.
export const VOLATILITY = film.final.volatility;
