import { book, D, MONTH_COUNT, monthName, prose, signed, weights } from "../../shared/data";
import { Formation } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, round } from "../layout";
import { asButton, box, chip, finder, SideCard, spark, stat } from "../ui";
import { C, dust, header, pick, Scene, stats, type World } from "./scene";
import { GOLDEN, seeded } from "../../shared/math";

// The positions (weights stored in 100000ths of the fund) and reasons.
const S = D.september.book.map(([ticker, name, w]) => ({ ticker, name: name || "Name not on file", weight: w / 1e5 }));
const WHY = new Map(D.explained.map((e) => [e.ticker, e]));
// August's tickers by side, so September can mark what is new.
const AUGUST = new Map(book(MONTH_COUNT - 1).map((x) => [D.stocks.ticker[x.stock], Math.sign(x.weight)]));
// Each pill's stocks: longs, shorts, or new since August by ticker.
const GROUPS = {
  long: (i: number) => S[i].weight > 0,
  short: (i: number) => S[i].weight < 0,
  fresh: (i: number) => !!S[i].ticker && AUGUST.get(S[i].ticker) !== Math.sign(S[i].weight),
};
type Group = keyof typeof GROUPS;
// Each past stock by ticker; of two sharing one, the latest held wins.
const PAST = new Map<string, number>();
for (let m = 0; m < MONTH_COUNT; m++) for (const x of book(m)) PAST.set(D.stocks.ticker[x.stock] ?? "", x.stock);

// A position's past: months in the book, and since when on this side.
function past(ticker: string, weight: number) {
  if (!ticker) return "No ticker on file, so its history cannot be traced.";
  const stock = PAST.get(ticker);
  if (stock === undefined) return "New to the book this month.";
  const w = weights(stock);
  const held = w.filter((v) => v !== 0).length;
  const side = Math.sign(weight);
  // Walk back from August while it held the same side.
  let start = MONTH_COUNT;
  while (start > 0 && Math.sign(w[start - 1] ?? 0) === side) start--;
  const months = `In the book ${held} of ${MONTH_COUNT} months`;
  if (start < MONTH_COUNT) return `${months}, ${side > 0 ? "long" : "short"} since ${monthName(D.months[start]!)}.`;
  let last = MONTH_COUNT - 1;
  while (last >= 0 && !w[last]) last--;
  return `New this month. ${months}, last in ${monthName(D.months[last]!)}.`;
}

// The first sentence of a written reason, short enough for a tooltip.
const gist = (why: string) => prose(why).split(/(?<=\.)\s/)[0];
// How far out the positions sit on their sphere, in scene units.
const RADIUS = 5.2;

// September's book: every position, the explainer's reasons for ten.
export class September extends Scene {
  name = "The book for September";
  summary = "What the final book holds now, with the explainer's reasons for ten positions.";
  private f = new Formation();
  private card: SideCard;
  private hovered = -1;
  // The pill pressed, whose stocks stay lit while the rest dim.
  private only: Group | null = null;
  private pills: HTMLElement[] = [];
  // Search over September's positions; a pick opens its card.
  private search = finder(
    "NRDS",
    "Not in the September book",
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
        "The book for <em>September</em>",
        "The same code, run one month past the record on data the backtest never saw. Longs sit above, shorts below, and gold ones come with a written reason.",
      ),
      stats(...this.pillsFor()),
    );
    this.controls.append(box("w-[min(320px,calc(100vw-32px))] gap-2", this.search.input, this.search.matches));
    this.card = new SideCard(this.w.layer, () => this.close());
    // Small screens fit the two discs and their ring into the band.
    this.frame = [...round(8.4, 0), ...corners(-5.4, -5.6, -5.4, 5.4, 5.6, 5.4)];
    this.zoomCap = 1.4;
  }

  // The three pills, each a toggle that lights its own stocks.
  private pillsFor() {
    const count = (g: Group) => String(S.filter((_, i) => GROUPS[g](i)).length);
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
        const told = WHY.has(S[i].ticker);
        // Out of the pressed pill's group, a stock shrinks and dims.
        const lit = !this.only || GROUPS[this.only](i) ? 1 : 0;
        const size = ((told ? 1.1 : 0.6) + Math.sqrt(Math.abs(S[i].weight) * 100) * 0.9) * (lit ? 1 : 0.6);
        const color = told ? C.gold : up > 0 ? C.cyan : C.orange;
        f.put(
          i,
          Math.cos(a) * ring * RADIUS,
          up * y * RADIUS,
          Math.sin(a) * ring * RADIUS,
          -size,
          color,
          (told ? 1.8 : 1.05) * (lit ? 1 : 0.18),
        );
      });
    place(longs, 1);
    place(shorts, -1);
    // A thin purple belt orbits just outside the sphere.
    const r = seeded(83);
    let k = S.length;
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

  // Opens a position's card with its reason.
  open(i: number) {
    const s = S[i];
    const why = WHY.get(s.ticker);
    this.w.sim.m.uSelect.value = i;
    const side = s.weight > 0 ? "Long" : "Short";
    // Every card shows the history, as slide 2 does; ten add the reason.
    const stock = s.ticker ? PAST.get(s.ticker) : undefined;
    const chart = stock === undefined ? [] : [h("div", { html: spark(stock, MONTH_COUNT - 1) })];
    const story = h("p", { class: "text-[13px] text-ink-2" }, past(s.ticker, s.weight));
    const reason = why ? [this.reason(why.why)] : [];
    this.card.show(`${s.ticker || "No ticker"} · ${side} ${signed(s.weight, 2)}`, s.name, ...chart, story, ...reason);
    if (why) {
      this.card.el.append(
        h(
          "p",
          { class: "text-[11px] text-ink-3" },
          "Written by a local model from the facts it was shown, every number checked",
        ),
      );
    }
    this.w.sound.tick(1.3, 0.7);
  }

  // The AI's reason as its first sentence, until Read all shows the rest.
  private reason(text: string) {
    const full = prose(text);
    const p = h("p", { class: "text-[13.5px] text-ink leading-relaxed" }, gist(text));
    if (p.textContent === full) return p;
    const more = chip("Read all", () => {
      p.textContent = full;
      more.remove();
    });
    return h("div", { class: "flex flex-col items-start gap-2" }, p, more);
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
    const why = WHY.get(s.ticker);
    const told = why ? `<br>${gist(why.why)}<br><span class="text-gold">Click for the full reason</span>` : "";
    return `<strong>${s.ticker || "No ticker"}</strong> <span class="muted">${s.name}</span><br>${s.weight > 0 ? "Long" : "Short"} ${signed(s.weight, 2)} of the fund${told}`;
  }

  // Opens the position under the pointer, or closes the card.
  override click() {
    if (this.hovered >= 0) this.open(this.hovered);
    else this.close();
  }
}
