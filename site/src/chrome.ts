import gsap from "gsap";
import { D, monthName } from "./data";
import type { Scene } from "./scenes/scene";
import { h } from "./ui";

const icon = (path: string) =>
  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
const PLAY = icon('<path d="M7 5l12 7-12 7z" fill="currentColor" stroke="none"/>');
const PAUSE = icon('<path d="M8 5v14M16 5v14"/>');
const SOUND = icon('<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 010 6M19 6.5a7.5 7.5 0 010 11"/>');
const MUTE = icon('<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M17 10l4 4M21 10l-4 4"/>');
const GRID = icon(
  '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
);

export interface Actions {
  go: (i: number) => void;
  tour: () => void;
  sound: () => void;
}

const KEYS = [
  ["→  ↓  Space", "Next scene"],
  ["←  ↑", "Previous scene"],
  ["0 to 9", "Jump to a scene"],
  ["O", "See every scene"],
  ["P", "Guided tour, hands free"],
  ["M", "Sound on or off"],
  ["E", "Explore freely, drag and scroll"],
  ["F", "Full screen"],
];

// Everything around the scenes: the header, the scene dots, the overview, help and the tour bar.
export class Chrome {
  private counter = h("span", { class: "figure" });
  private tourButton: HTMLButtonElement;
  private soundButton: HTMLButtonElement;
  private bar = h("div", { class: "absolute left-0 top-0 h-[2px] bg-purple shadow-[0_0_12px_var(--purple)]" });
  private tourBar = h("div", { class: "absolute left-0 top-[2px] h-[2px] bg-gold opacity-0" });
  private dots = h("nav", { class: "dots", "aria-label": "Scenes" });
  private help: HTMLElement;
  private overview: HTMLElement;
  private tiles: HTMLButtonElement[] = [];

  constructor(
    layer: HTMLElement,
    private scenes: Scene[],
    actions: Actions,
  ) {
    const button = (html: string, label: string, onClick: () => void) => {
      const b = h("button", {
        class: "chip icon-chip help-button",
        type: "button",
        "aria-label": label,
        title: label,
        html,
      });
      b.addEventListener("click", onClick);
      return b as HTMLButtonElement;
    };
    this.tourButton = button(PLAY, "Guided tour (P)", actions.tour);
    this.soundButton = button(MUTE, "Sound (M)", actions.sound);
    const overview = button(`${GRID}`, "Every scene (O)", () => this.toggleOverview());
    overview.append(this.counter);
    const help = button("?", "Keys (?)", () => this.toggleHelp());
    const brand = h(
      "header",
      { class: "brand" },
      h("span", { class: "headline text-[22px] text-ink" }, "QUARCC Purple"),
      h("span", { class: "eyebrow hidden md:inline" }, "FIAM · Finals 2026"),
    );
    const top = h("div", { class: "topbar" }, this.tourButton, this.soundButton, overview, help);
    scenes.forEach((s, i) => {
      const b = h("button", { type: "button", "aria-label": s.name }, h("span", {}, s.name));
      b.addEventListener("click", () => actions.go(i));
      this.dots.append(b);
    });
    const first = monthName(D.months[0], true);
    const last = monthName(D.months[D.months.length - 1], true);
    const foot = h(
      "p",
      { class: "eyebrow hint foot" },
      `Backtest ${first} to ${last} after every modelled cost · not a live record`,
    );
    this.help = h(
      "div",
      { class: "sheet", role: "dialog", "aria-label": "Keys" },
      h(
        "div",
        { class: "glass rounded-2xl p-6 flex flex-col gap-3 text-[14px] text-ink-2 min-w-[300px]" },
        h("p", { class: "headline text-[30px] text-ink" }, "Getting around"),
        ...KEYS.map(([k, v]) => h("div", { class: "flex justify-between gap-8" }, h("kbd", {}, k), h("span", {}, v))),
        h(
          "p",
          { class: "text-[12px] text-ink-3 pt-1" },
          "Click anything that glows. Click empty space to send a ripple.",
        ),
      ),
    );
    this.help.addEventListener("click", () => this.toggleHelp(false));
    const grid = h("div", { class: "overview-grid" });
    scenes.forEach((s, i) => {
      const tile = h(
        "button",
        { type: "button", class: "tile glass" },
        h("span", { class: "figure text-[12px] text-ink-3" }, String(i).padStart(2, "0")),
        h("span", { class: "headline text-[24px] text-ink" }, s.name),
        h("span", { class: "text-[13px] text-ink-2 leading-snug" }, s.summary),
      ) as HTMLButtonElement;
      tile.addEventListener("click", () => {
        this.toggleOverview(false);
        actions.go(i);
      });
      this.tiles.push(tile);
      grid.append(tile);
    });
    this.overview = h(
      "div",
      { class: "sheet overview", role: "dialog", "aria-label": "Every scene" },
      h("p", { class: "eyebrow" }, "Every scene · press a number or click a card"),
      grid,
    );
    this.overview.addEventListener("click", (e) => {
      if (e.target === this.overview) this.toggleOverview(false);
    });
    layer.append(brand, top, this.bar, this.tourBar, this.dots, foot, this.help, this.overview);
  }

  get open() {
    return this.help.classList.contains("on") || this.overview.classList.contains("on");
  }

  update(index: number) {
    const last = this.scenes.length - 1;
    this.counter.textContent = `${String(index).padStart(2, "0")} / ${String(last).padStart(2, "0")}`;
    gsap.to(this.bar, { width: `${(index / last) * 100}%`, duration: 0.8, ease: "power3.out" });
    this.dots.querySelectorAll("button").forEach((b, k) => b.setAttribute("aria-current", String(k === index)));
    this.tiles.forEach((t, k) => t.classList.toggle("current", k === index));
  }

  toggleHelp(on = !this.help.classList.contains("on")) {
    this.help.classList.toggle("on", on);
    if (on) this.toggleOverview(false);
  }

  toggleOverview(on = !this.overview.classList.contains("on")) {
    this.overview.classList.toggle("on", on);
    if (on) {
      this.help.classList.remove("on");
      gsap.fromTo(
        this.tiles,
        { opacity: 0, y: 24, scale: 0.96 },
        { opacity: 1, y: 0, scale: 1, duration: 0.6, stagger: 0.035, ease: "power3.out" },
      );
    }
  }

  close() {
    this.toggleHelp(false);
    this.toggleOverview(false);
  }

  setTour(on: boolean) {
    this.tourButton.innerHTML = on ? PAUSE : PLAY;
    this.tourButton.setAttribute("aria-pressed", String(on));
    gsap.to(this.tourBar, { opacity: on ? 1 : 0, duration: 0.4 });
  }

  tourProgress(share: number) {
    this.tourBar.style.width = `${Math.min(1, share) * 100}%`;
  }

  setSound(on: boolean) {
    this.soundButton.innerHTML = on ? SOUND : MUTE;
    this.soundButton.setAttribute("aria-pressed", String(on));
  }
}
