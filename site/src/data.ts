import raw from "./data/fiam.json";

export interface Row {
  capital: number;
  ir: number;
  net: number;
  cost: number;
  dollars: number;
}

export interface Agent {
  key: string;
  name: string;
  model: string;
  does: string;
  facts: [string, string][];
}

export interface Family {
  what: string;
  family: string;
  eligible: boolean;
  attempts: number;
  result: string;
  verdict: string;
}

export interface Fiam {
  book: string;
  code: string;
  window: string;
  months: string[];
  headline: Record<string, number> & {
    best_month: { month: string; value: number };
    worst_month: { month: string; value: number };
  };
  years: Record<string, { strategy: number; benchmark: number; market: number; active: number; months: number }>;
  race: { book: number[]; hurdle: number[]; market: number[]; market_monthly: number[]; book_monthly: number[] };
  beta: { exante: number[]; rolling: Record<string, [number, number]>; outside_noise: number };
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
    break_even_cost: number;
    ladder: { multiple: number; cost: number; active: number; ir: number }[];
  };
  edge: {
    irs: number[];
    draws: number;
    final: number;
    best: number;
    mean: number;
    p5: number;
    p95: number;
    beaten: number;
    live_low: number;
    live_high: number;
    ladder: { label: string; ir: number; kind: string }[];
  };
  capacity: { books: { key: string; label: string; break_even: number | string; peak: number; rows: Row[] }[] };
  crowd: {
    personas: { key: string; client: string }[];
    agents: number;
    copycats: number;
    effective_voters: number;
    correlation: number;
    same_information: number;
    same_persona: number;
    rerun_agreement: number;
    longs_in_favourites: number;
    shorts_in_favourites: number;
    copycat_longs: number;
    copycat_test: Record<string, { longs: number; shorts: number }>;
    crowd_beta: number;
    crowd_t: number;
    picks: number;
    models: string[];
    model_agreement: number;
    likes: Record<string, number>;
  };
  agents: Agent[];
  explained: { ticker: string; side: string; why: string }[];
  september: { decision: string; book: [string, string, number][] };
  factor_story: string;
  crises: Record<string, number>;
  honesty: {
    attempts: number;
    eligible: number;
    dsr_all: number;
    dsr_eligible: number;
    first_half_ir: number;
    second_half_ir: number;
    check_2016_2020_ir: number;
    families: Family[];
  };
}

export const D = raw as unknown as Fiam;

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

// Text from the data read as plain sentences: a dash between numbers becomes "to", any other dash a
// comma, and a colon or semicolon ends the sentence.
export const prose = (text: string) =>
  text
    .replace(/(\d)\s*[\u2013\u2014]\s*(\d)/g, "$1 to $2")
    .replace(/\s*[\u2013\u2014]\s*/g, ", ")
    .replace(/\s*[:;]\s+(\S)/g, (_, c: string) => `. ${c.toUpperCase()}`);

// A short title from the data on one line: a colon or semicolon becomes a middle dot.
export const caption = (text: string) => prose(text.replace(/\s*[:;]\s+/g, " · "));

export const pct = (x: number, digits = 1) => `${x < 0 ? "−" : ""}${Math.abs(x * 100).toFixed(digits)}%`;
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : "−"}${Math.abs(x * 100).toFixed(digits)}%`;
export const num = (x: number, digits = 2) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(digits);
export const plus = (x: number, digits = 2) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(digits);
export const int = (x: number) => Math.round(x).toLocaleString("en-US");
export const money = (x: number) =>
  x >= 1e9
    ? `$${+(x / 1e9).toFixed(1)}B`
    : x >= 1e6
      ? `$${+(x / 1e6).toFixed(1)}M`
      : x >= 1e5
        ? `$${(x / 1e6).toFixed(2)}M`
        : `$${int(x)}`;
export const monthName = (m: string, short = false) => {
  const name = MONTHS[+m.slice(5, 7) - 1];
  return `${short ? name.slice(0, 3) : name} ${m.slice(0, 4)}`;
};

export interface Holding {
  stock: number;
  weight: number;
}

export const book = (month: number): Holding[] => {
  const flat = D.stocks.book[month];
  const out: Holding[] = [];
  for (let i = 0; i < flat.length; i += 2) out.push({ stock: flat[i], weight: flat[i + 1] / 1000 });
  return out;
};

export const STOCKS = D.stocks.ticker.length;
export const MONTH_COUNT = D.months.length;

let history: Float32Array[] | null = null;

export const weights = (stock: number): Float32Array => {
  if (!history) {
    history = Array.from({ length: STOCKS }, () => new Float32Array(MONTH_COUNT));
    for (let m = 0; m < MONTH_COUNT; m++) for (const h of book(m)) history[h.stock][m] = h.weight;
  }
  return history[stock];
};

export const yearIndex = (year: string) => D.months.findIndex((m) => m.startsWith(year));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const clamp = (x: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, x));

export const at = (rows: Row[], capital: number, key: keyof Row) => {
  const x = Math.log10(capital);
  const xs = rows.map((r) => Math.log10(r.capital));
  if (x <= xs[0]) return rows[0][key];
  for (let i = 1; i < rows.length; i++) {
    if (x <= xs[i]) return lerp(rows[i - 1][key], rows[i][key], (x - xs[i - 1]) / (xs[i] - xs[i - 1]));
  }
  return rows[rows.length - 1][key];
};
