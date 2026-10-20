import gsap from "gsap";
import type { Scene } from "./scenes/scene";
import { TEAM } from "../content/credits";
import { h } from "../shared/dom";
import { coarse } from "./layout";
import { chip } from "./ui";

// A 16 px line icon in the text colour, and the five the controls use.
const icon = (path: string) =>
  `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
const PLAY = icon('<path d="M7 5l12 7-12 7z" fill="currentColor" stroke="none"/>');
const PAUSE = icon('<path d="M8 5v14M16 5v14"/>');
const SOUND = icon('<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 010 6M19 6.5a7.5 7.5 0 010 11"/>');
const MUTE = icon('<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M17 10l4 4M21 10l-4 4"/>');
const GRID = icon(
  '<rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/>',
);

// What the controls can ask the tour to do.
export interface Actions {
  go: (i: number) => void;
  tour: () => void;
  sound: () => void;
}

// The help sheet's rows: the keys, then what they do.
const KEYS = [
  ["→  ↓  Space", "Next scene"],
  ["←  ↑", "Previous scene"],
  ["0 to 9", "Jump to a scene"],
  ["O", "See every scene"],
  ["P", "Guided tour, hands free"],
  ["M", "Sound on or off"],
  ["F", "Full screen"],
];
// The same help for a finger, gestures in place of keys.
const TOUCH = [
  ["Swipe", "Next or previous scene"],
  ["Grid", "See every scene"],
  ["Play", "Guided tour, hands free"],
];

// The chrome round the scenes: header, dots, overview, help, tour bar.
export class Chrome {
  private counter = h("span", { class: "figure" });
  private tourButton: HTMLButtonElement;
  private soundButton: HTMLButtonElement;
  // Progress lines: purple for the scene, gold under it for the tour.
  private bar = h("div", { class: "absolute left-0 top-0 h-[2px] bg-purple shadow-[0_0_12px_var(--purple)]" });
  private tourBar = h("div", { class: "absolute left-0 top-[2px] h-[2px] bg-gold opacity-0" });
  private dots = h("nav", { class: "dots", "aria-label": "Scenes" });
  // On small screens: a thumb bar of back, the scene's name, and next.
  private dock = h("nav", { class: "dock", "aria-label": "Scene steps" });
  private where = h("button", { class: "chip where", type: "button" }) as HTMLButtonElement;
  private steps: HTMLButtonElement[] = [];
  private help: HTMLElement;
  private overview: HTMLElement;
  private tiles: HTMLButtonElement[] = [];
  private index = 0;
  // Panel state for Back: shown, entry pushed, and unwinding that entry.
  private shown = false;
  private pushed = false;
  private unwinding = false;
  private opener: HTMLElement | null = null;

  // Builds the chrome into the layer and wires each control to actions.
  constructor(
    layer: HTMLElement,
    private scenes: Scene[],
    actions: Actions,
  ) {
    // A header button: an icon chip named for screen readers and on hover.
    const button = (html: string, label: string, onClick: () => void, pressed?: boolean) => {
      const b = chip(html, onClick, pressed);
      b.classList.add("icon-chip", "help-button");
      b.setAttribute("aria-label", label);
      b.title = label;
      return b;
    };
    // Header chips at top right, the counter inside the overview chip.
    this.tourButton = button(PLAY, "Guided tour (P)", actions.tour, false);
    this.soundButton = button(MUTE, "Sound (M)", actions.sound, false);
    const overview = button(`${GRID}`, "Every scene (O)", () => this.toggleOverview());
    overview.append(this.counter);
    const help = button("?", "Keys (?)", () => this.toggleHelp());
    // The team's names top left, on screens wide enough for one line.
    const brand = h(
      "header",
      { class: "brand" },
      h("span", { class: "eyebrow text-ink-2 whitespace-nowrap hidden xl:inline" }, TEAM.join("  ·  ")),
    );
    const top = h("div", { class: "topbar" }, this.tourButton, this.soundButton, overview, help);
    scenes.forEach((s, i) => {
      // A dot per scene down the right edge, its name shown on hover.
      const b = h("button", { type: "button", "aria-label": s.name }, h("span", {}, s.name));
      b.addEventListener("click", () => actions.go(i));
      this.dots.append(b);
    });
    // The help sheet lists the keys; a click anywhere on it closes it.
    this.help = h(
      "div",
      { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": "Keys", tabindex: "-1" },
      h(
        "div",
        { class: "glass rounded-2xl p-6 flex flex-col gap-3 text-[14px] text-ink-2 min-w-[300px]" },
        h("p", { class: "headline text-[30px] text-ink" }, "Getting around"),
        ...(coarse() ? TOUCH : KEYS).map(([k, v]) =>
          h("div", { class: "flex justify-between gap-8" }, h("kbd", {}, k), h("span", {}, v)),
        ),
        h(
          "p",
          { class: "text-[12px] text-ink-3 pt-1" },
          coarse()
            ? "Tap anything that glows. Tap empty space to send a ripple."
            : "Click anything that glows. Click empty space to send a ripple.",
        ),
      ),
    );
    this.help.addEventListener("click", () => this.toggleHelp(false));
    // The overview: a card per scene with its number, name and summary.
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
      { class: "sheet overview", role: "dialog", "aria-modal": "true", "aria-label": "Every scene", tabindex: "-1" },
      h(
        "p",
        { class: "eyebrow" },
        coarse() ? "Every scene · tap a card" : "Every scene · press a number or click a card",
      ),
      grid,
    );
    // Only a click on the backdrop, not on a card, closes the overview.
    this.overview.addEventListener("click", (e) => {
      if (e.target === this.overview) this.toggleOverview(false);
    });
    // The thumb bar's arrows step scenes, its middle opens every scene.
    const step = (text: string, label: string, by: number) => {
      const b = chip(text, () => actions.go(this.index + by));
      b.setAttribute("aria-label", label);
      b.classList.add("step");
      this.steps.push(b);
      return b;
    };
    this.where.addEventListener("click", () => this.toggleOverview());
    this.dock.append(step("‹", "Previous scene", -1), this.where, step("›", "Next scene", 1));
    layer.append(brand, top, this.bar, this.tourBar, this.dots, this.dock, this.help, this.overview);
    // Tab and Shift+Tab cycle the open panel's buttons, never leaving it.
    for (const sheet of [this.help, this.overview]) {
      sheet.addEventListener("keydown", (e) => {
        if (e.key !== "Tab") return;
        e.preventDefault();
        const items = [...sheet.querySelectorAll<HTMLElement>("button")];
        if (!items.length) return;
        const at = items.indexOf(document.activeElement as HTMLElement);
        items[e.shiftKey ? (at <= 0 ? items.length - 1 : at - 1) : (at + 1) % items.length].focus();
      });
    }
    // Back closes an open panel, and the address keeps naming the scene.
    addEventListener("popstate", () => {
      if (this.unwinding) this.unwinding = false;
      else if (this.pushed) {
        this.pushed = false;
        this.close();
      } else return;
      history.replaceState(null, "", `#${this.index}`);
    });
  }

  // Whether help or the overview is up; the tour waits while it is.
  get open() {
    return this.help.classList.contains("on") || this.overview.classList.contains("on");
  }

  // Marks the current scene in the counter, bar, dots and overview cards.
  update(index: number) {
    const last = this.scenes.length - 1;
    this.index = index;
    this.counter.textContent = `${String(index).padStart(2, "0")} / ${String(last).padStart(2, "0")}`;
    gsap.to(this.bar, { width: `${(index / last) * 100}%`, duration: 0.8, ease: "power3.out" });
    this.dots.querySelectorAll("button").forEach((b, k) => b.setAttribute("aria-current", String(k === index)));
    this.tiles.forEach((t, k) => t.classList.toggle("current", k === index));
    this.where.innerHTML = `<b>${String(index).padStart(2, "0")}</b> ${this.scenes[index]?.name ?? ""}`;
    this.steps.forEach((b, k) => (b.disabled = k === 0 ? index === 0 : index === last));
  }

  // Opens or closes the key help; opening it closes the overview.
  toggleHelp(on = !this.help.classList.contains("on")) {
    this.help.classList.toggle("on", on);
    if (on) this.toggleOverview(false);
    this.sync();
  }

  // Opens or closes the overview; opening closes help, cards rising in.
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
    this.sync();
  }

  // An entry in history lets Back shut a panel; focus goes in and back.
  private sync() {
    const panel = [this.help, this.overview].find((p) => p.classList.contains("on"));
    // Opening remembers the focused element and pushes one history entry.
    if (panel && !this.shown) {
      this.opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      if (!this.pushed) history.pushState({ panel: true }, "");
      this.pushed = true;
    } else if (!panel && this.shown) {
      // Closing pops the entry it pushed and gives focus back to the opener.
      if (this.pushed) {
        this.pushed = false;
        this.unwinding = true;
        history.back();
      }
      if (this.opener && this.opener !== document.body) this.opener.focus({ preventScroll: true });
      else (document.activeElement as HTMLElement | null)?.blur();
      this.opener = null;
    }
    this.shown = !!panel;
    panel?.focus({ preventScroll: true });
  }

  // Closes help and the overview, as Escape and the number keys do.
  close() {
    this.toggleHelp(false);
    this.toggleOverview(false);
  }

  // Swaps play for pause and fades the gold tour line in or out.
  setTour(on: boolean) {
    this.tourButton.innerHTML = on ? PAUSE : PLAY;
    this.tourButton.setAttribute("aria-pressed", String(on));
    gsap.to(this.tourBar, { opacity: on ? 1 : 0, duration: 0.4 });
  }

  // Fills the gold tour line by the share of the dwell, capped at full.
  tourProgress(share: number) {
    this.tourBar.style.width = `${Math.min(1, share) * 100}%`;
  }

  // Swaps the muted icon for the speaker, and its pressed state.
  setSound(on: boolean) {
    this.soundButton.innerHTML = on ? SOUND : MUTE;
    this.soundButton.setAttribute("aria-pressed", String(on));
  }
}
