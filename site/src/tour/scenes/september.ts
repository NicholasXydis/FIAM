import { book, D, MONTH_COUNT, monthName, pct, signed, weights } from "../../shared/data";
import { Formation } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, round } from "../layout";
import { asButton, box, finder, fold, SideCard, spark, stat } from "../ui";
import { C, dust, header, pick, Scene, stats, type World } from "./scene";
import { GOLDEN, seeded } from "../../shared/math";

// The positions, weights stored in 100000ths of the fund.
const S = D.september.book.map(([ticker, name, w]) => ({ ticker, name: name || "Name not on file", weight: w / 1e5 }));
// The book's month, the record's last, and the month before it.
const NOW = MONTH_COUNT - 1;
// The month before's tickers by side, so the book can mark what is new.
const BEFORE = new Map(book(NOW - 1).map((x) => [D.stocks.ticker[x.stock], Math.sign(x.weight)]));
// Each pill's stocks: longs, shorts, or new since the month before.
const GROUPS = {
  long: (i: number) => S[i].weight > 0,
  short: (i: number) => S[i].weight < 0,
  fresh: (i: number) => !!S[i].ticker && BEFORE.get(S[i].ticker) !== Math.sign(S[i].weight),
};
// Carbon Arc's card spend check of the book, as totals only.
const HYPE = D.september.hype;
// The name of one pill's group of stocks.
type Group = keyof typeof GROUPS;
// Each past stock by ticker; of two sharing one, the latest held wins.
const PAST = new Map<string, number>();
// Walk every month's book, so later months overwrite earlier.
for (let m = 0; m < MONTH_COUNT; m++) for (const x of book(m)) PAST.set(D.stocks.ticker[x.stock] ?? "", x.stock);

// A position's past: months in the book, and since when on this side.
function past(ticker: string, weight: number) {
  if (!ticker) return "No ticker on file, so its history cannot be traced.";
  const stock = PAST.get(ticker);
  if (stock === undefined) return "New to the book this month.";
  const w = weights(stock);
  const held = w.filter((v) => v !== 0).length;
  const side = Math.sign(weight);
  // Walk back from the book's month while it held the same side.
  let start = NOW;
  while (start > 0 && Math.sign(w[start - 1] ?? 0) === side) start--;
  const months = `In the book ${held} of ${MONTH_COUNT} months`;
  if (start < NOW) return `${months}, ${side > 0 ? "long" : "short"} since ${monthName(D.months[start]!)}.`;
  // Else find the last month before this one that held it.
  let last = NOW - 1;
  while (last >= 0 && !w[last]) last--;
  if (last < 0) return "New to the book this month.";
  return `New this month. ${months}, last in ${monthName(D.months[last]!)}.`;
}

// How far out the positions sit on their sphere, in scene units.
const RADIUS = 5.2;

// What the fund holds now: every position of the final book.
export class September extends Scene {
  name = "What the fund holds now";
  summary = "Every position of the final book on its last day, with a Carbon Arc check.";
  private f = new Formation();
  private card: SideCard;
  private hovered = -1;
  // The pill pressed, whose stocks stay lit while the rest dim.
  private only: Group | null = null;
  private pills: HTMLElement[] = [];
  // Search over the book's positions; a pick opens its card.
  private search = finder(
    S[0]?.ticker ?? "",
    "Not in the final book",
    S.map((s) => s.ticker),
    D.september.book.map((b) => b[1]),
    (i) => this.open(i),
  );

  // Lays out the sphere once, then the panel and the reason card.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 3.2, 17.5], look: [0, 0, 0], drift: 0.7, shift: 0.14 };
    this.physics = { stiff: 10, damp: 1.15, flow: 0.18, spin: 0.05, mouse: 0.9 };
    this.dwell = 15;
    this.build();
    this.panel.append(
      ...header(
        "What the fund <em>holds now</em>",
        `The final book at the close of ${monthName(D.september.month)}. Carbon Arc checks it against real card spend.`,
      ),
      stats(...this.pillsFor()),
    );
    this.controls.append(
      box("w-[min(320px,calc(100vw-32px))] gap-2", ...this.hype(), this.search.input, this.search.matches),
    );
    // Small screens fold the card spend rows behind a Carbon Arc chip.
    const glass = this.controls.firstElementChild as HTMLElement;
    const head = glass.firstElementChild as HTMLElement;
    fold(glass, head, [...glass.children].slice(1, 5), "Carbon Arc");
    this.card = new SideCard(this.w.layer, () => this.close());
    // Small screens fit the two discs and their ring into the band.
    this.frame = [...round(8.4, 0), ...corners(-5.4, -5.6, -5.4, 5.4, 5.6, 5.4)];
    this.zoomCap = 1.4;
  }

  // Hype against the cash register: card spend by side, totals only.
  private hype() {
    // One row: what it measures and its value.
    const row = (label: string, value: string) =>
      h(
        "div",
        { class: "flex justify-between gap-3 text-[13px] border-t border-line pt-1" },
        h("span", { class: "text-ink-2" }, label),
        h("b", { class: "figure text-ink font-medium text-right" }, value),
      );
    return [
      h(
        "div",
        { class: "flex items-center justify-between gap-3" },
        h("p", { class: "eyebrow" }, "Hype vs the cash register"),
      ),
      row("Card spend, our longs", signed(HYPE.long_growth, 2)),
      row("Card spend, our shorts", signed(HYPE.short_growth, 2)),
      row(
        "AI crowd favourites in Hype",
        `${HYPE.in_hype} of ${HYPE.favourites}, ${pct(HYPE.in_hype / HYPE.favourites, 0)}`,
      ),
      h("p", { class: "text-[11px] text-ink-3" }, "Neutral to the shopper. A check after the fact, never in the fund."),
    ];
  }

  // The three pills, each a toggle that lights its own stocks.
  private pillsFor() {
    // How many of the book's stocks fall in a group.
    const count = (g: Group) => String(S.filter((_, i) => GROUPS[g](i)).length);
    // One pill: its count and label, a toggle for its group.
    const make = (g: Group, label: string) => {
      const el = asButton(stat(count(g), label).el, () => this.light(this.only === g ? null : g));
      el.setAttribute("aria-pressed", "false");
      return el;
    };
    this.pills = [make("long", "Longs"), make("short", "Shorts"), make("fresh", "New this month")];
    return this.pills;
  }

  // Lights one group's stocks and dims the rest, or lights them all.
  light(group: Group | null) {
    this.only = group;
    const keys: Group[] = ["long", "short", "fresh"];
    this.pills.forEach((p, i) => p.setAttribute("aria-pressed", String(keys[i] === group)));
    this.build();
    if (this.active) this.w.sim.update(this.f);
  }

  // Longs on the upper half-sphere, shorts below, biggest at the poles.
  private build() {
    const f = this.f;
    const order = S.map((_, i) => i);
    const longs = order.filter((i) => S[i].weight > 0);
    const shorts = order.filter((i) => S[i].weight < 0).reverse();
    // A golden-angle spiral from the pole; negative size makes each orbit.
    const place = (list: number[], up: number) =>
      list.forEach((i, k) => {
        const y = 0.14 + 0.86 * (1 - (k + 0.5) / list.length);
        const ring = Math.sqrt(1 - y * y);
        const a = k * GOLDEN;
        // Out of the pressed pill's group, a stock shrinks and dims.
        const lit = !this.only || GROUPS[this.only](i) ? 1 : 0;
        const size = (0.6 + Math.sqrt(Math.abs(S[i].weight) * 100) * 0.9) * (lit ? 1 : 0.6);
        const color = up > 0 ? C.cyan : C.orange;
        f.put(
          i,
          Math.cos(a) * ring * RADIUS,
          up * y * RADIUS,
          Math.sin(a) * ring * RADIUS,
          -size,
          color,
          1.05 * (lit ? 1 : 0.18),
        );
      });
    place(longs, 1);
    place(shorts, -1);
    // A thin purple belt orbits just outside the sphere.
    const r = seeded(83);
    let k = S.length;
    // 2600 small points on a flat ring, at random angles.
    for (let j = 0; j < 2600; j++, k++) {
      const a = r() * Math.PI * 2;
      const d = RADIUS + 1.4 + r() * 1.6;
      f.put(k, Math.cos(a) * d, (r() - 0.5) * 0.25, Math.sin(a) * d, -(0.2 + r() * 0.2), C.purple, 0.35 + r() * 0.3);
    }
    dust(f, k, 61, 36, 1.6, 0.12);
  }

  // The sphere laid out once in the constructor.
  formation() {
    return this.f;
  }

  // Opens a position's card with its history.
  open(i: number) {
    const s = S[i];
    this.w.sim.m.uSelect.value = i;
    const side = s.weight > 0 ? "Long" : "Short";
    // Every card shows the history, as slide 2 does.
    const stock = s.ticker ? PAST.get(s.ticker) : undefined;
    const chart = stock === undefined ? [] : [h("div", { html: spark(stock, NOW) })];
    const story = h("p", { class: "text-[13px] text-ink-2" }, past(s.ticker, s.weight));
    this.card.show(`${s.ticker || "No ticker"} · ${side} ${signed(s.weight, 2)}`, s.name, ...chart, story);
    this.w.sound.tick(1.3, 0.7);
  }

  // Closes the card and clears the selection glow.
  close() {
    this.card.hide();
    this.w.sim.m.uSelect.value = -1;
  }

  // Closes the card and lights every stock again on the way out.
  override leave() {
    this.close();
    if (this.only) this.light(null);
  }

  // Highlights the position under the pointer.
  override hover(x: number, y: number) {
    const i = pick(this.f, 0, S.length, x, y, this.w, 18);
    this.hovered = i;
    this.w.sim.m.uHover.value = i;
    if (i < 0) return null;
    const s = S[i];
    return `<strong>${s.ticker || "No ticker"}</strong> <span class="muted">${s.name}</span><br>${s.weight > 0 ? "Long" : "Short"} ${signed(s.weight, 2)} of the fund`;
  }

  // Opens the position under the pointer, or closes the card.
  override click() {
    if (this.hovered >= 0) this.open(this.hovered);
    else this.close();
  }
}
