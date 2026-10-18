import { D, monthName, num, plus } from "../shared/data";
import { PEOPLE } from "./team";

// The record's window in words, such as "January 2021 to August 2026".
const WINDOW = `${monthName(D.months[0]!)} to ${monthName(D.months.at(-1)!)}`;

// Counts to twenty in words, as a sentence reads them.
const WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
  "twenty",
];
const spell = (n: number) => WORDS[n] ?? String(n);
// The same, capitalised to open a sentence.
const opening = (n: number) => spell(n).replace(/^./, (c) => c.toUpperCase());

// What frames every page: the name and the backtest's disclaimer.
const FRAME = {
  name: "QUARCC Purple",
  disclaimer: `Backtested results, ${WINDOW}, after modelled costs. Not a live record and not an offer to invest.`,
};

// Each page's words, worked out here at build and sent to it as JSON.
export const CONTENT = {
  landing: {
    ...FRAME,
    eyebrow: "McGill-FIAM Asset Management Hackathon 2026 Finals",
    title: "Calm,",
    gold: "by design.",
    lead: `A market-neutral book of US stocks. ${opening(D.signals.length)} published measures pick the stocks, machine learning keeps the book neutral, and ${spell(D.agents.length)} AI agents check the work on our own machines.`,
    figures: [
      {
        label: `Sharpe ratio ${num(D.headline.sharpe)} after costs`,
        text: `The return earned for each unit of risk, ${WINDOW}, after every modelled cost.`,
      },
      {
        label: `Beta ${plus(D.headline.beta)} to the S&P 500`,
        text: `How far the book moves with the market. Zero would mean not at all, and the measured beta is ${plus(D.headline.beta)} with a standard error of ${num(D.headline.beta_se)}.`,
      },
      {
        label: `${D.agents.length} AI agents, run locally`,
        text: "They read filings, check the rules and argue against the book, all on our own machines. None of them sets a position.",
      },
    ],
  },
  team: {
    ...FRAME,
    title: "The team",
    lead: "The people behind QUARCC Purple's book, its research and its AI.",
    people: PEOPLE,
  },
  missing: {
    ...FRAME,
    title: "This page does not exist.",
    lead: "The address may be mistyped, or the page may have moved.",
  },
};

// The pages by name, each with the words it is given.
export type Content = typeof CONTENT;
