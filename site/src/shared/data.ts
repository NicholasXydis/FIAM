import raw from "../data/fiam.json";
import { mix } from "./math";

// One fund size's results in the capacity table, capital in dollars.
export interface Row {
  capital: number;
  ir: number;
  net: number;
  cost: number;
  dollars: number;
}

// One AI agent as the tour shows it; facts are [label, value] pairs.
interface Agent {
  key: string;
  name: string;
  model: string;
  does: string;
  facts: [string, string][];
}

// One family of attempts in the research ledger.
interface Family {
  what: string;
  family: string;
  eligible: boolean;
  attempts: number;
  verdict: string;
}

// The headline's single-number measures the tour shows.
type Measure =
  | "ir"
  | "net"
  | "gross"
  | "cagr"
  | "vol"
  | "sharpe"
  | "drawdown"
  | "alpha"
  | "beta"
  | "correlation"
  | "hit"
  | "positions"
  | "longs"
  | "shorts";

// Everything the site draws, as tools/build_site.py writes it.
export interface Fiam {
  book: string;
  code: string;
  window: string;
  months: string[];
  headline: Record<Measure, number>;
  years: Record<string, { strategy: number; benchmark: number; market: number; active: number; months: number }>;
  race: { book: number[]; hurdle: number[]; market: number[]; market_monthly: number[]; book_monthly: number[] };
  beta: { exante: number[]; rolling: Record<string, [number, number]> };
  stocks: { ticker: string[]; name: string[]; book: number[][] };
  signals: { code: string; sign: number; family: string; label: string }[];
  families: Record<string, string>;
  journey: { month: string; stocks: number; tradeable: number; longs: number; shorts: number };
  costs: {
    gross: number;
    net: number;
    parts: Record<string, number>;
    total: number;
    break_even_multiple: number;
    ladder: { multiple: number; cost: number; active: number; ir: number }[];
  };
  edge: {
    irs: number[];
    draws: number;
    final: number;
    best: number;
    mean: number;
    beaten: number;
    ladder: { label: string; ir: number; kind: string }[];
  };
  capacity: { books: { key: string; label: string; break_even: number | string; rows: Row[] }[] };
  crowd: {
    personas: { key: string; client: string }[];
    agents: number;
    copycats: number;
    effective_voters: number;
    correlation: number;
    longs_in_favourites: number;
    copycat_test: Record<string, { longs: number; shorts: number }>;
    picks: number;
  };
  agents: Agent[];
  explained: { ticker: string; side: string; why: string }[];
  september: { decision: string; book: [string, string, number][] };
  crises: Record<string, number>;
  honesty: {
    attempts: number;
    eligible: number;
    dsr_eligible: number;
    families: Family[];
  };
}

// The data as tools/build_site.py writes it; bundled, never fetched.
export const D = raw as unknown as Fiam;

// Month names for monthName, January first.
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

// Data text made plain: ranges read "to", dashes commas, colons a stop.
export const prose = (text: string) =>
  text
    .replace(/(\d)\s*[\u2013\u2014]\s*(\d)/g, "$1 to $2")
    .replace(/\s*[\u2013\u2014]\s*/g, ", ")
    .replace(/\s*[:;]\s+(\S)/g, (_, c: string) => `. ${c.toUpperCase()}`);

// A one-line title from data text: a colon or semicolon becomes " · ".
export const caption = (text: string) => prose(text.replace(/\s*[:;]\s+/g, " · "));

// Fractions as percents with a true minus sign; signed always signs.
export const pct = (x: number, digits = 1) => `${x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%`;
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(digits)}%`;
// Plain numbers with a true minus sign; plus always signs.
export const num = (x: number, digits = 2) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(digits);
export const plus = (x: number, digits = 2) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(digits);
// Whole numbers with thousands commas, as in 12,345.
export const int = (x: number) => Math.round(x).toLocaleString("en-US");
// Dollars as $2B or $1.5M, from $100,000 as $0.10M, below that whole.
export const money = (x: number) =>
  x >= 1e9
    ? `$${+(x / 1e9).toFixed(1)}B`
    : x >= 1e6
      ? `$${+(x / 1e6).toFixed(1)}M`
      : x >= 1e5
        ? `$${(x / 1e6).toFixed(2)}M`
        : `$${int(x)}`;
// A "2021-03" month as "March 2021", or "Mar 2021" when short.
export const monthName = (m: string, short = false) => {
  const name = MONTHS[+m.slice(5, 7) - 1]!;
  return `${short ? name.slice(0, 3) : name} ${m.slice(0, 4)}`;
};

// One position: the stock's index and its weight.
export interface Holding {
  stock: number;
  weight: number;
}

// One month's book, unpacked from the flat [stock, weight × 1000] list.
export const book = (month: number): Holding[] => {
  const flat = D.stocks.book[month]!;
  const out: Holding[] = [];
  for (let i = 0; i < flat.length; i += 2) out.push({ stock: flat[i]!, weight: flat[i + 1]! / 1000 });
  return out;
};

// How many stocks and months the data spans.
export const STOCKS = D.stocks.ticker.length;
export const MONTH_COUNT = D.months.length;

// weights()'s cache, one Float32Array of months per stock.
let history: Float32Array[] | null = null;

// A stock's weight in every month, built once on first use.
export const weights = (stock: number): Float32Array => {
  if (!history) {
    history = Array.from({ length: STOCKS }, () => new Float32Array(MONTH_COUNT));
    for (let m = 0; m < MONTH_COUNT; m++) for (const h of book(m)) history[h.stock]![m] = h.weight;
  }
  return history[stock]!;
};

// Index of a year's first month in D.months, or -1 if it has none.
export const yearIndex = (year: string) => D.months.findIndex((m) => m.startsWith(year));

// A capacity table read at any capital, log-scale between its rows.
export const at = (rows: Row[], capital: number, key: keyof Row) => {
  const x = Math.log10(capital);
  const xs = rows.map((r) => Math.log10(r.capital));
  if (x <= xs[0]!) return rows[0]![key];
  for (let i = 1; i < rows.length; i++) {
    if (x <= xs[i]!) return mix(rows[i - 1]![key], rows[i]![key], (x - xs[i - 1]!) / (xs[i]! - xs[i - 1]!));
  }
  return rows[rows.length - 1]![key];
};
