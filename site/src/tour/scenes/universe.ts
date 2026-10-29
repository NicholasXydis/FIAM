import gsap from "gsap";
import { book, D, int, MONTH_COUNT, monthName, pct, signed, STOCKS, weights } from "../../shared/data";
import { Formation } from "../gl/sim";
import { h } from "../../shared/dom";
import { corners, round } from "../layout";
import { box, fill, finder, fold, Label, months, type Player, SideCard, spark, stat, swatch } from "../ui";
import { C, dust, header, pick, Scene, stats, type World } from "./scene";
import { GOLDEN, seeded } from "../../shared/math";

// Height of the long and short discs.
const LIFT = 3.6;
// Seconds per month while Play runs.
const STEP = 0.62;
// A stock's ticker, or a stand-in when it has none.
const ticker = (i: number) => D.stocks.ticker[i] || "No ticker";

// Every stock we held, between the long and short discs, searchable.
export class Universe extends Scene {
  name = "The book, month by month";
  summary = "Every stock we held, flying between the long and short groups. Search any ticker.";
  month = 0;
  private f = new Formation();
  private input: HTMLInputElement;
  // Search over every stock held; a pick opens it at a month it was held.
  private search = finder("NVDA", "No stock by that name was held", D.stocks.ticker, D.stocks.name, (i) =>
    this.find(i),
  );
  private when = h("b", { class: "figure text-[28px] text-ink font-medium" });
  private player: Player;
  private counts = {
    longs: stat("", "Stocks long"),
    shorts: stat("", "Stocks short"),
    gross: stat("", "Gross exposure"),
    net: stat("", "Net exposure"),
  };
  private long = this.addLabel(new Label("", [0, LIFT + 1.4, 0], "center"));
  private short = this.addLabel(new Label("", [0, -LIFT - 1.4, 0], "center"));
  private card: SideCard;
  private hovered = -1;
  private selected = -1;
  private halo: Float32Array;

  // Seeds every stock a spot in the outer halo, then panel and search.
  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 7.5, 21], look: [0, 0, 0], drift: 0.8 };
    this.physics = { stiff: 7, damp: 1.15, flow: 0.25, spin: 0.05, mouse: 0.8 };
    this.dwell = 22;
    const r = seeded(11);
    this.halo = new Float32Array(STOCKS * 3);
    // Give every stock a random spot in a wide flat ring.
    for (let i = 0; i < STOCKS; i++) {
      const a = r() * Math.PI * 2;
      const d = 8.5 + r() * 3.2;
      this.halo.set([Math.cos(a) * d, (r() - 0.5) * 1.1, Math.sin(a) * d], i * 3);
    }
    this.panel.append(
      ...header(
        "Every stock, <em>month by month</em>",
        "Stocks with the best forecasts rise to the long group, the worst sink to the short group and the rest wait in the outer ring. Click any stock for its history.",
      ),
      stats(...Object.values(this.counts).map((s) => s.el)),
    );
    const picker = months("month", STEP, this);
    this.player = picker.player;
    this.input = picker.input;
    const first = monthName(D.months[0], true);
    const last = monthName(D.months[MONTH_COUNT - 1], true);
    this.controls.append(
      box(
        "w-[min(420px,calc(100vw-32px))] gap-2",
        h("div", { class: "flex items-center justify-between gap-3" }, this.when, this.player.button),
        this.input,
        h("div", { class: "flex justify-between eyebrow" }, h("span", {}, first), h("span", {}, last)),
        this.search.input,
        this.search.matches,
      ),
    );
    this.card = new SideCard(this.w.layer, () => this.close());
    // Small screens: the search folds behind Find, the slider's ends drop.
    const glass = this.controls.firstElementChild as HTMLElement;
    fold(glass, glass.firstElementChild as HTMLElement, [this.search.input, this.search.matches], "Find");
    glass.children[2]?.classList.add("ends");
    this.frame = [...round(10.5, 0), ...corners(-3.6, -5.2, -3.6, 3.6, 5.2, 3.6)];
  }

  // Longs fill the top disc, shorts the bottom, the rest orbit the halo.
  formation() {
    const f = this.f;
    const held = book(this.month);
    const longs = held.filter((x) => x.weight > 0).sort((a, b) => b.weight - a.weight);
    const shorts = held.filter((x) => x.weight < 0).sort((a, b) => a.weight - b.weight);
    const placed = new Uint8Array(STOCKS);
    // A golden-angle spiral, biggest weight at the centre, sized by weight.
    const seat = (list: typeof held, y: number, color: number) =>
      list.forEach((x, k) => {
        const d = 0.34 * Math.sqrt(k + 0.6);
        const a = k * GOLDEN;
        const size = 0.55 + Math.sqrt(Math.abs(x.weight)) * 1.25;
        const glow = 1 + Math.abs(x.weight) * 0.5;
        f.put(x.stock, Math.cos(a) * d, y + Math.sin(k * 1.7) * 0.06, Math.sin(a) * d, size, color, glow);
        placed[x.stock] = 1;
      });
    seat(longs, LIFT, C.cyan);
    seat(shorts, -LIFT, C.orange);
    // Stocks not held this month sit dim in the outer halo.
    for (let i = 0; i < STOCKS; i++) {
      if (!placed[i]) f.put(i, this.halo[i * 3], this.halo[i * 3 + 1], this.halo[i * 3 + 2], -0.42, C.dust, 0.42);
    }
    // The formation is reused, so dust is laid only the first time.
    if (!f.col[(STOCKS + 1) * 4 + 3]) dust(f, STOCKS, 5, 34, 1.6, 0.16);
    // Weights are in percent, so gross and net divide by 100.
    const gross = held.reduce((s, x) => s + Math.abs(x.weight), 0) / 100;
    const net = held.reduce((s, x) => s + x.weight, 0) / 100;
    this.counts.longs.value.textContent = int(longs.length);
    this.counts.shorts.value.textContent = int(shorts.length);
    this.counts.gross.value.textContent = pct(gross);
    this.counts.net.value.textContent = pct(Math.abs(net) < 0.0005 ? 0 : net);
    this.long.set(`${swatch("var(--m-long)")}Long · ${longs.length}`);
    this.short.set(`${swatch("var(--m-short)")}Short · ${shorts.length}`);
    this.when.textContent = monthName(D.months[this.month], true);
    return f;
  }

  // Shows a month's book in place, keeping any open card current.
  set(month: number) {
    this.month = month;
    this.input.value = String(month);
    fill(this.input);
    this.w.sim.update(this.formation());
    if (this.selected >= 0) this.open(this.selected);
  }

  // Opens a stock at its last held month up to now, else its first.
  find(i: number) {
    this.player.stop();
    const w = weights(i);
    let month = -1;
    for (let m = this.month; m >= 0 && month < 0; m--) if (w[m]) month = m;
    if (month < 0) month = w.findIndex((v) => v !== 0);
    this.set(month);
    this.open(i);
    this.w.sound.tick(1.2);
  }

  // Shows disc labels, and plays 2.2 s in if still on the first month.
  override enter() {
    this.long.shown = this.short.shown = true;
    gsap.delayedCall(2.2, () => this.active && this.month === 0 && this.player.start());
  }

  // Stops and closes on the way out.
  override leave() {
    this.player.stop();
    this.close();
  }

  // Space plays or pauses.
  override key(e: KeyboardEvent) {
    return this.player.key(e);
  }

  // Highlights the stock under the pointer.
  override hover(x: number, y: number) {
    const i = pick(this.f, 0, STOCKS, x, y, this.w, 18);
    this.hovered = i;
    this.w.sim.m.uHover.value = i;
    if (i < 0) return null;
    const w = weights(i);
    const now = w[this.month];
    const months = w.reduce((n, v) => n + (v ? 1 : 0), 0);
    const when = monthName(D.months[this.month], true);
    return `<strong>${ticker(i)}</strong> <span class="muted">${D.stocks.name[i]}</span><br>${now > 0 ? "Long" : "Short"} ${signed(now / 100, 2)} in ${when} · held ${months} of ${MONTH_COUNT} months`;
  }

  // Opens the stock under the pointer, or closes the card.
  override click() {
    if (this.hovered >= 0) this.open(this.hovered);
    else this.close();
  }

  // Opens a stock's card with its weight in every month.
  open(i: number) {
    this.selected = i;
    this.w.sim.m.uSelect.value = i;
    const w = weights(i);
    const months = w.reduce((n, v) => n + (v ? 1 : 0), 0);
    const longs = w.reduce((n, v) => n + (v > 0 ? 1 : 0), 0);
    const largest = pct(Math.max(...Array.from(w, Math.abs)) / 100, 2);
    this.card.show(
      ticker(i),
      D.stocks.name[i],
      h("div", { html: spark(i, this.month) }),
      h(
        "p",
        { class: "text-[13px] text-ink-2" },
        `Held ${months} of ${MONTH_COUNT} months, ${longs} long and ${months - longs} short. Largest weight ${largest}.`,
      ),
    );
  }

  // Closes the card and clears the selection glow.
  close() {
    this.selected = -1;
    this.w.sim.m.uSelect.value = -1;
    this.card.hide();
  }
}
