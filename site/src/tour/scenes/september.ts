import { D, int, pct, prose, signed } from "../../shared/data";
import { Formation } from "../gl/sim";
import { h } from "../../shared/dom";
import { chip, SideCard, stat } from "../ui";
import { C, dust, header, pick, Scene, stats, type World } from "./scene";
import { GOLDEN, seeded } from "../../shared/math";

// The positions (weights stored in 100000ths of the fund) and reasons.
const S = D.september.book.map(([ticker, name, w]) => ({ ticker, name: name || "Name not on file", weight: w / 1e5 }));
const WHY = new Map(D.explained.map((e) => [e.ticker, e]));
// Long count, gross and net exposure, and the sphere's radius.
const LONGS = S.filter((s) => s.weight > 0).length;
const GROSS = S.reduce((t, s) => t + Math.abs(s.weight), 0);
const NET = S.reduce((t, s) => t + s.weight, 0);
const RADIUS = 5.2;

// September's book: every position, the explainer's reasons for ten.
export class September extends Scene {
  name = "The book for September";
  summary = "What the final book holds now, with the explainer's reasons for ten positions.";
  private f = new Formation();
  private card: SideCard;
  private told = S.map((s, i) => (WHY.has(s.ticker) ? i : -1)).filter((i) => i >= 0);
  private hovered = -1;
  private chips: HTMLButtonElement[] = [];

  // Lays out the sphere once, and the chips for the ten written up.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 3.2, 17.5], look: [0, 0, 0], drift: 0.7, shift: 0.14 };
    this.physics = { stiff: 10, damp: 1.15, flow: 0.18, spin: 0.05, mouse: 0.9 };
    this.dwell = 15;
    this.build();
    this.panel.append(
      ...header(
        "September 2026 · decided on 31 August 2026",
        "The book for <em>September</em>",
        "The same code, run one month past the record on data the backtest never saw. This is what the final book holds now, longs above and shorts below. Gold marks the ten positions our explainer agent wrote up. Click one to read why we hold it.",
      ),
      stats(
        stat(int(S.length), `Positions, ${LONGS} long and ${S.length - LONGS} short`).el,
        stat(pct(GROSS), "Gross exposure").el,
        stat(pct(Math.abs(NET) < 0.0005 ? 0 : NET), "Net exposure").el,
      ),
    );
    this.chips = this.told.map((i) => chip(S[i].ticker, () => this.open(i), false));
    this.controls.append(
      h(
        "div",
        { class: "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2" },
        h("p", { class: "eyebrow" }, "Written up by the explainer"),
        h("div", { class: "flex flex-wrap gap-1.5" }, ...this.chips),
      ),
    );
    this.card = new SideCard(this.w.layer, () => this.close());
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
        const size = (told ? 1.1 : 0.6) + Math.sqrt(Math.abs(S[i].weight) * 100) * 0.9;
        const color = told ? C.gold : up > 0 ? C.cyan : C.orange;
        f.put(
          i,
          Math.cos(a) * ring * RADIUS,
          up * y * RADIUS,
          Math.sin(a) * ring * RADIUS,
          -size,
          color,
          told ? 1.8 : 1.05,
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
    this.chips.forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === s.ticker)));
    const side = s.weight > 0 ? "Long" : "Short";
    this.card.show(
      `${s.ticker || "No ticker"} · ${side} ${signed(s.weight, 2)}`,
      s.name,
      why
        ? h("p", { class: "text-[13.5px] text-ink-2 leading-relaxed" }, prose(why.why))
        : h(
            "p",
            { class: "text-[13px] text-ink-3" },
            "The explainer wrote up ten positions, and this is not one of them.",
          ),
    );
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

  // Closes the card and clears the selection glow and chips.
  close() {
    this.card.hide();
    this.w.sim.m.uSelect.value = -1;
    this.chips.forEach((c) => c.setAttribute("aria-pressed", "false"));
  }

  // Closes the card on the way out.
  override leave() {
    this.close();
  }

  // Highlights the position under the pointer.
  override hover(x: number, y: number) {
    const i = pick(this.f, 0, S.length, x, y, this.w, 18);
    this.hovered = i;
    this.w.sim.m.uHover.value = i;
    if (i < 0) return null;
    const s = S[i];
    const told = WHY.has(s.ticker) ? `<br><span class="text-gold">Click to read why we hold it</span>` : "";
    return `<strong>${s.ticker || "No ticker"}</strong> <span class="muted">${s.name}</span><br>${s.weight > 0 ? "Long" : "Short"} ${signed(s.weight, 2)} of the fund${told}`;
  }

  // Opens the position under the pointer, or closes the card.
  override click() {
    if (this.hovered >= 0) this.open(this.hovered);
    else this.close();
  }
}
