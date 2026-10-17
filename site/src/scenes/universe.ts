import gsap from "gsap";
import { book, D, int, MONTH_COUNT, monthName, pct, signed, STOCKS, weights } from "../data";
import { Formation } from "../gl/sim";
import { chip, h, Label, slider, stat, swatch } from "../ui";
import { C, dust, pick, rand, Scene, type World } from "./scene";

const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const LIFT = 3.6;
const STEP = 0.62;
const ticker = (i: number) => D.stocks.ticker[i] || "No ticker";

// One stock's weight in every month as bars on a zero line, longs above in cyan and shorts below.
function spark(stock: number, month: number) {
  const w = weights(stock);
  const W = 292;
  const H = 76;
  const top = Math.max(0.2, ...Array.from(w, Math.abs));
  const x = (i: number) => (i / (MONTH_COUNT - 1)) * W;
  const y = (v: number) => H / 2 - (v / top) * (H / 2 - 6);
  const bars = Array.from(w, (v, i) => {
    if (!v) return "";
    const color = v > 0 ? "var(--m-long)" : "var(--m-short)";
    const height = Math.max(1, Math.abs(y(v) - H / 2));
    return `<rect x="${x(i) - 1.6}" y="${Math.min(y(v), H / 2)}" width="3.2" height="${height}" rx="1.2" fill="${color}"/>`;
  }).join("");
  const now = x(month);
  return `<svg viewBox="-4 0 ${W + 8} ${H}" width="100%" height="${H}" role="img" aria-label="Weight by month">
    <line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" stroke="rgb(237 233 246 / .25)" stroke-width="1"/>
    ${bars}
    <line x1="${now}" x2="${now}" y1="2" y2="${H - 2}" stroke="var(--ink)" stroke-width="1" stroke-dasharray="2 3"/>
  </svg>`;
}

export class Universe extends Scene {
  name = "The book, month by month";
  summary = "Every stock we held, flying between the long and short discs. Search any ticker.";
  month = 0;
  playing = false;
  private f = new Formation();
  private input: HTMLInputElement;
  private search = h("input", {
    class: "search",
    type: "search",
    placeholder: "Find a stock, like NVDA",
    "aria-label": "Find a stock",
    autocomplete: "off",
    spellcheck: "false",
  }) as HTMLInputElement;
  private matches = h("div", { class: "flex flex-wrap gap-1.5 empty:hidden" });
  private when = h("b", { class: "figure text-[28px] text-ink font-medium" });
  private play = chip("Play", () => (this.playing ? this.stop() : this.start()), false);
  private counts = {
    longs: stat("", "Stocks long"),
    shorts: stat("", "Stocks short"),
    gross: stat("", "Gross exposure"),
    net: stat("", "Net exposure"),
  };
  private long = this.addLabel(new Label("", [0, LIFT + 1.4, 0], "center"));
  private short = this.addLabel(new Label("", [0, -LIFT - 1.4, 0], "center"));
  private card = h("aside", { class: "card glass", hidden: true });
  private hovered = -1;
  private selected = -1;
  private timer: gsap.core.Tween | null = null;
  private halo: Float32Array;

  constructor(w: World) {
    super(w);
    this.shot = { eye: [0, 7.5, 21], look: [0, 0, 0], drift: 0.8 };
    this.physics = { stiff: 7, damp: 1.15, flow: 0.25, spin: 0.05, mouse: 0.8 };
    this.dwell = 22;
    const r = rand(11);
    this.halo = new Float32Array(STOCKS * 3);
    for (let i = 0; i < STOCKS; i++) {
      const a = r() * Math.PI * 2;
      const d = 8.5 + r() * 3.2;
      this.halo.set([Math.cos(a) * d, (r() - 0.5) * 1.1, Math.sin(a) * d], i * 3);
    }
    this.panel.append(
      h("p", { class: "eyebrow", "data-rise": true }, `${int(STOCKS)} stocks · ${D.months.length} months`),
      h("h2", {
        class: "headline text-[44px] md:text-[56px]",
        "data-rise": true,
        html: "Every stock we held, <em>month by month</em>",
      }),
      h(
        "p",
        { class: "body", "data-rise": true },
        "The best scores rise into the long disc and the worst sink into the short disc, sized by weight. Everything else waits in the outer ring. Hover a stock to see its name, click it for its history, or search for one.",
      ),
      h("div", { class: "stats", "data-rise": true }, ...Object.values(this.counts).map((s) => s.el)),
    );
    this.input = slider("month", "Month", 0, MONTH_COUNT - 1, 1, 0);
    this.input.addEventListener("input", () => {
      this.stop();
      this.set(+this.input.value);
    });
    this.search.addEventListener("input", () => this.suggest());
    this.search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") (this.matches.firstElementChild as HTMLButtonElement | null)?.click();
      if (e.key === "Escape") this.search.blur();
    });
    const first = monthName(D.months[0], true);
    const last = monthName(D.months[MONTH_COUNT - 1], true);
    this.controls.append(
      h(
        "div",
        { class: "glass rounded-2xl px-4 py-3 w-[min(420px,calc(100vw-32px))] flex flex-col gap-2" },
        h("div", { class: "flex items-center justify-between gap-3" }, this.when, this.play),
        this.input,
        h("div", { class: "flex justify-between eyebrow" }, h("span", {}, first), h("span", {}, last)),
        this.search,
        this.matches,
      ),
    );
    this.card.style.right = "max(56px, env(safe-area-inset-right, 0px))";
    this.card.style.top = "72px";
    this.w.layer.append(this.card);
  }

  formation() {
    const f = this.f;
    const held = book(this.month);
    const longs = held.filter((x) => x.weight > 0).sort((a, b) => b.weight - a.weight);
    const shorts = held.filter((x) => x.weight < 0).sort((a, b) => a.weight - b.weight);
    const placed = new Uint8Array(STOCKS);
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
    for (let i = 0; i < STOCKS; i++) {
      if (!placed[i]) f.put(i, this.halo[i * 3], this.halo[i * 3 + 1], this.halo[i * 3 + 2], -0.42, C.dust, 0.42);
    }
    if (!f.col[(STOCKS + 1) * 4 + 3]) dust(f, STOCKS, 5, 34, 1.6, 0.16);
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

  set(month: number) {
    this.month = month;
    this.input.value = String(month);
    this.input.style.setProperty("--fill", `${(month / (MONTH_COUNT - 1)) * 100}%`);
    this.w.sim.update(this.formation());
    if (this.selected >= 0) this.open(this.selected);
  }

  start() {
    if (this.month >= MONTH_COUNT - 1) this.set(0);
    this.playing = true;
    this.play.textContent = "Pause";
    this.play.setAttribute("aria-pressed", "true");
    const next = () => {
      if (!this.playing || !this.active) return;
      if (this.month >= MONTH_COUNT - 1) return this.stop();
      this.set(this.month + 1);
      this.timer = gsap.delayedCall(STEP, next);
    };
    this.timer = gsap.delayedCall(STEP, next);
  }

  stop() {
    this.playing = false;
    this.timer?.kill();
    this.play.textContent = "Play";
    this.play.setAttribute("aria-pressed", "false");
  }

  // Up to six stocks whose ticker starts with, or whose name contains, what was typed.
  suggest() {
    const q = this.search.value.trim().toUpperCase();
    this.matches.innerHTML = "";
    if (!q) return;
    const hits: number[] = [];
    for (let i = 0; i < STOCKS && hits.length < 6; i++) if (D.stocks.ticker[i].startsWith(q)) hits.push(i);
    for (let i = 0; i < STOCKS && hits.length < 6; i++) {
      if (!hits.includes(i) && D.stocks.name[i].toUpperCase().includes(q)) hits.push(i);
    }
    if (!hits.length)
      this.matches.append(h("span", { class: "text-[12px] text-ink-3" }, "No stock by that name was held"));
    for (const i of hits) this.matches.append(chip(ticker(i), () => this.find(i)));
  }

  // Shows a stock in a month it was held, the latest one up to the current month if there is one.
  find(i: number) {
    this.stop();
    const w = weights(i);
    let month = -1;
    for (let m = this.month; m >= 0 && month < 0; m--) if (w[m]) month = m;
    if (month < 0) month = w.findIndex((v) => v !== 0);
    this.set(month);
    this.open(i);
    this.w.sound.tick(1.2);
  }

  enter() {
    this.long.shown = this.short.shown = true;
    gsap.delayedCall(2.2, () => this.active && this.month === 0 && this.start());
  }

  leave() {
    this.stop();
    this.close();
  }

  key(e: KeyboardEvent) {
    if (e.key !== " ") return false;
    if (this.playing) this.stop();
    else this.start();
    return true;
  }

  hover(x: number, y: number) {
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

  click() {
    if (this.hovered >= 0) this.open(this.hovered);
    else this.close();
  }

  open(i: number) {
    this.selected = i;
    this.w.sim.m.uSelect.value = i;
    const w = weights(i);
    const months = w.reduce((n, v) => n + (v ? 1 : 0), 0);
    const longs = w.reduce((n, v) => n + (v > 0 ? 1 : 0), 0);
    const largest = pct(Math.max(...Array.from(w, Math.abs)) / 100, 2);
    this.card.hidden = false;
    this.card.innerHTML = "";
    this.card.append(
      h(
        "div",
        { class: "flex items-start justify-between gap-3" },
        h(
          "div",
          {},
          h("p", { class: "eyebrow" }, ticker(i)),
          h("p", { class: "headline text-[26px]" }, D.stocks.name[i]),
        ),
        chip("Close", () => this.close()),
      ),
      h("div", { html: spark(i, this.month) }),
      h(
        "p",
        { class: "text-[13px] text-ink-2" },
        `Held ${months} of ${MONTH_COUNT} months, ${longs} long and ${months - longs} short. Largest weight ${largest}.`,
      ),
    );
  }

  close() {
    this.selected = -1;
    this.w.sim.m.uSelect.value = -1;
    this.card.hidden = true;
  }
}
