import raw from "../data/fiam.json";

// One AI agent as the tour shows it, and its finding on the final book.
interface Agent {
  key: string;
  name: string;
  model: string;
  does: string;
  finding: string;
  number: string;
  date: string;
}

// A 60/40 with some of its bonds in the fund: points moved and results.
interface Step {
  fund: number;
  cagr: number;
  vol: number;
  drawdown: number;
}

// One replayed crisis: its window and the market's and book's moves.
interface Crisis {
  name: string;
  first: string;
  last: string;
  market: number;
  book: number;
  coverage: number;
}

// The headline's single-number measures the tour shows.
type Measure =
  | "ir"
  | "ir_gross"
  | "net"
  | "gross"
  | "cagr"
  | "vol"
  | "sharpe"
  | "drawdown"
  | "alpha"
  | "beta"
  | "beta_monthly"
  | "correlation"
  | "hit"
  | "positions"
  | "longs"
  | "shorts"
  | "breaches"
  | "sector_max"
  | "cumulative"
  | "months_up"
  | "down_capture"
  | "up_capture";

// One month and the fund's return over it, or over the 12 to it.
interface Dated {
  month: string;
  value: number;
}

// Everything the site draws, as tools/build_site.py writes it.
export interface Fiam {
  window: string;
  months: string[];
  headline: Record<Measure, number> & { best_month: Dated; worst_month: Dated; worst_12: Dated };
  years: Record<string, { strategy: number; benchmark: number; market: number; active: number; months: number }>;
  race: { book: number[]; hurdle: number[]; market: number[]; market_monthly: number[]; book_monthly: number[] };
  beta: { rolling: Record<string, [number, number]>; since: Record<string, number> };
  stocks: { ticker: string[]; name: string[]; book: number[][] };
  signals: { code: string; family: string; label: string; count: number }[];
  families: Record<string, string>;
  journey: { month: string; stocks: number; tradeable: number; longs: number; shorts: number; average: number };
  costs: {
    gross: number;
    net: number;
    hurdle: number;
    cash: number;
    break_even: number;
    parts: Record<string, number>;
    total: number;
    ir_gross: number;
    turnover: number;
  };
  edge: {
    year_2022: { sp500: number; bonds: number; sixty_forty: number; fund: number };
    steps: Step[];
    window: string;
    source: string;
  };
  sp500: { vol: number; drawdown: number };
  crowd: {
    personas: { key: string; client: string }[];
    agents: number;
    copycats: number;
    effective_voters: number;
    lsv: number;
    beta: number;
    sell_10bn_pct: number;
    long_pct: number;
    short_pct: number;
    favourites_pct: number;
  };
  agents: Agent[];
  september: {
    month: string;
    book: [string, string, number][];
    hype: {
      long_growth: number;
      short_growth: number;
      longs: number;
      shorts: number;
      favourites: number;
      in_hype: number;
    };
  };
  crises: Crisis[];
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

// Data text made plain: ranges say "to", dashes commas, a true minus.
export const prose = (text: string) =>
  text
    .replace(/(\d)\s*[\u2013\u2014]\s*(\d)/g, "$1 to $2")
    .replace(/\s*[\u2013\u2014]\s*/g, ", ")
    .replace(/\s*[:;]\s+(\S)/g, (_, c: string) => `. ${c.toUpperCase()}`)
    .replace(/(^|\s)-(\d)/g, "$1\u2212$2");

// A one-line title from data text: a colon or semicolon becomes " · ".
export const caption = (text: string) => prose(text.replace(/\s*[:;]\s+/g, " · "));

// A fraction as a percent with a true minus sign.
export const pct = (x: number, digits = 1) => `${x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%`;
// A fraction as a percent that always shows its sign.
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(digits)}%`;
// A plain number with a true minus sign.
export const num = (x: number, digits = 2) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(digits);
// A plain number that always shows its sign.
export const plus = (x: number, digits = 2) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(digits);
// A whole number as an ordinal, as in 1st, 22nd, 57th or 112th.
export const ordinal = (n: number) => {
  const end = n % 100 >= 10 && n % 100 <= 20 ? "th" : (["th", "st", "nd", "rd"][n % 10] ?? "th");
  return `${n}${end}`;
};
// Whole numbers with thousands commas, as in 12,345.
export const int = (x: number) => Math.round(x).toLocaleString("en-US");
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
