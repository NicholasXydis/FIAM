# Finals deck films from its charts' results, each ending on the still.

import json
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.animation import FFMpegWriter  # noqa: E402

from fiam import book as P  # noqa: E402
from fiam.paths import ARCHIVE  # noqa: E402
from fiam.paths import read_json as load  # noqa: E402
from fiam.report.animation import ease  # noqa: E402
from fiam.report.charts import ALT, BENCH, INK, MUTED, OURS  # noqa: E402
from fiam.report.runs import CAPITALS, final_run  # noqa: E402

CLIPS = Path("out") / "figures" / "clips"
FPS, DPI = 30, 160
GOLD = "#B07D2B"
# The AI crowd film's night palette, so the dot films match it.
NAVY, LIGHT, WHITE, DIM, ORANGE, SUN = (
    "#0B1F33", "#5CC8E0", "#FFFFFF", "#8A9BB0", "#E07A3F", "#F2C14E",
)  # fmt: skip
# Each book's colour and name, the final book drawn heaviest.
BOOKS = {
    "v1": (OURS, "First book"),
    "v2": (ALT, "Built for size"),
    "v2-pass": (GOLD, "Short rule only"),
    "final v3": (INK, "Final book"),
}
plt.rcParams.update(
    {
        "font.family": ["Calibri", "DejaVu Sans"],
        "font.size": 13,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "axes.edgecolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
    }
)


# The house axis style: no top or right spine, light gridlines behind.
def tidy(ax) -> None:
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E6EAEE", lw=0.8)
    ax.set_axisbelow(True)


# Films draw(t) for t in [0, seconds], the first frame as the poster.
def film(name: str, figsize, seconds: float, draw, face: str = "white", dpi: int = DPI) -> None:
    CLIPS.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=figsize, dpi=dpi, facecolor=face)
    quality = ["-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow", "-movflags", "+faststart"]
    writer = FFMpegWriter(fps=FPS, codec="libx264", extra_args=quality)
    target = CLIPS / f"{name}.mp4"
    with writer.saving(fig, str(target), dpi=dpi):
        for i, t in enumerate(np.arange(int(FPS * seconds)) / FPS):
            fig.clf()
            draw(fig, t)
            writer.grab_frame(facecolor=face)
            if i == 0:
                fig.savefig(CLIPS / f"{name}.png", dpi=dpi, facecolor=face)
    plt.close(fig)
    print(f"wrote {target} ({seconds:.1f} s, {target.stat().st_size / 1e6:.1f} MB)")


# A line drawn to progress p in [0, 1], the tip interpolated to glide.
def partial(x: np.ndarray, y: np.ndarray, p: float) -> tuple[np.ndarray, np.ndarray]:
    k = p * (len(x) - 1)
    n = int(np.floor(k))
    if n >= len(x) - 1:
        return x, y
    frac = k - n
    tip_x = x[n] + (x[n + 1] - x[n]) * frac
    tip_y = y[n] + (y[n + 1] - y[n]) * frac
    return np.append(x[: n + 1], tip_x), np.append(y[: n + 1], tip_y)


# Seats n dots in a sunflower around a centre, so a group packs evenly.
def seats(n: int, centre: tuple, gap: float) -> np.ndarray:
    k = np.arange(n)
    r, spin = gap * np.sqrt(k + 0.5), k * 2.39996
    return np.column_stack([centre[0] + r * np.cos(spin), centre[1] + r * np.sin(spin)])


# Moves points from a to b over time t, each with its own small delay.
def glide(a: np.ndarray, b: np.ndarray, t: float, start: float, delay: np.ndarray) -> np.ndarray:
    p = ease((t - start - delay) / 1.1)[:, None]
    return a + (b - a) * p


# How a stock earns its place: a real month kept, scored, ranked, held.
def journey() -> None:
    from fiam import data

    run = final_run(1e7)
    held = data.read(ARCHIVE / run / "record" / "holdings.parquet")
    month = held["eom"].max()
    book = held[held["eom"] == month].set_index("permno")["weight"]
    panel = P.load_panel()
    every = panel[panel["eom"] == month].reset_index(drop=True)
    day = f"{month:%Y-%m-%d}"
    scored = P.build_signal(P.screen(panel, day, day)).set_index("permno")["composite"]
    n = len(every)
    rng = np.random.default_rng(3)
    angle, radius = rng.uniform(0, 2 * np.pi, n), np.sqrt(rng.uniform(0, 1, n))
    cloud = np.column_stack([8 + 6.6 * radius * np.cos(angle), 4.4 + 2.5 * radius * np.sin(angle)])
    score = every["permno"].map(scored)
    kept = score.notna().to_numpy()
    rank = score.rank(pct=True).fillna(0.5).to_numpy()
    band = np.column_stack([1.3 + 13.4 * rank, 4.1 + rng.uniform(-0.45, 0.45, n)])
    # Stocks we cannot trade stay where they faded, out of the ranking.
    band[~kept] = cloud[~kept]
    weight = every["permno"].map(book).fillna(0.0).to_numpy()
    longs, shorts = np.flatnonzero(weight > 0), np.flatnonzero(weight < 0)
    group = band.copy()
    group[longs[np.argsort(-rank[longs])]] = seats(len(longs), (11.7, 4.3), 0.105)
    group[shorts[np.argsort(rank[shorts])]] = seats(len(shorts), (4.3, 4.3), 0.105)
    chosen = weight != 0
    delay = rng.uniform(0, 0.45, n)
    paint = matplotlib.colors.LinearSegmentedColormap.from_list("score", [ORANGE, DIM, LIGHT])
    lit = paint(rank)
    lead = [
        (0.2, f"{n:,} US stocks", f"One month, {month:%B %Y}"),
        (1.9, f"{kept.sum():,} we can trade", "The rest are too small or too cheap"),
        (3.4, "Twelve signals, one score", "Published research, nothing fitted to our test years"),
        (5.0, "Ranked worst to best", ""),
        (
            6.8,
            f"{len(longs)} long, {len(shorts)} short",
            "The best and the worst, sized by our optimizer",
        ),
        (8.9, "Zero net bet", "On the market and on every sector"),
    ]

    # Frame at t: dots fade in, rank, the book gathers, then the level beam.
    def draw(fig, t):
        ax = fig.add_axes((0, 0, 1, 1), facecolor=NAVY)
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 9)
        ax.axis("off")
        where = glide(cloud, band, t, 5.0, delay * kept)
        where = np.where(chosen[:, None], glide(where, group, t, 6.8, delay), where)
        alpha = np.full(n, ease(t / 0.8)) * np.minimum(1, rng.uniform(0.6, 1.4, n))
        alpha = np.where(kept, alpha, alpha * (1 - 0.92 * ease((t - 1.9) / 0.8)))
        alpha = np.where(chosen | ~kept, alpha, alpha * (1 - 0.88 * ease((t - 6.8) / 1.0)))
        colour = np.tile(matplotlib.colors.to_rgba(DIM), (n, 1))
        colour = colour + (lit - colour) * ease((t - 3.4) / 1.0)
        mine = ease((t - 7.4) / 0.8)
        colour[longs] = colour[longs] + (matplotlib.colors.to_rgba(LIGHT) - colour[longs]) * mine
        colour[shorts] = (
            colour[shorts] + (matplotlib.colors.to_rgba(ORANGE) - colour[shorts]) * mine
        )
        colour[:, 3] = np.clip(alpha, 0, 1)
        size = np.where(chosen, 7 + 22 * ease((t - 6.8) / 1.2), 7.0)
        ax.scatter(where[:, 0], where[:, 1], s=size, c=colour, linewidths=0)
        ends = ease((t - 5.6) / 0.6) * (1 - ease((t - 6.8) / 0.5))
        if ends > 0:
            ax.text(1.3, 3.25, "Worst", color=ORANGE, fontsize=18, alpha=ends, ha="left")
            ax.text(14.7, 3.25, "Best", color=LIGHT, fontsize=18, alpha=ends, ha="right")
        sides = ease((t - 7.6) / 0.6)
        if sides > 0:
            ax.text(4.3, 2.55, "Short", color=ORANGE, fontsize=20, ha="center", alpha=sides)
            ax.text(11.7, 2.55, "Long", color=LIGHT, fontsize=20, ha="center", alpha=sides)
        beam = ease((t - 8.9) / 0.9)
        if beam > 0:
            half = 5.2 * beam
            ax.plot([8 - half, 8 + half], [1.75, 1.75], color=WHITE, lw=4, solid_capstyle="round")
            ax.add_patch(plt.Polygon([[7.7, 1.25], [8.3, 1.25], [8, 1.7]], color=SUN, alpha=beam))
        for i, (start, head, sub) in enumerate(lead):
            stop = lead[i + 1][0] if i + 1 < len(lead) else 99
            a = ease((t - start) / 0.5) * (1 - ease((t - stop + 0.35) / 0.35))
            if a > 0:
                ax.text(8, 7.9, head, color=WHITE, fontsize=40, weight="bold", ha="center", alpha=a)
                ax.text(8, 7.2, sub, color=DIM, fontsize=19, ha="center", alpha=a)

    film("journey", (16, 9), 11.5, draw, face=NAVY, dpi=120)
    told = dict(month=f"{month:%B %Y}", stocks=n, tradeable=int(kept.sum()))
    told |= dict(longs=len(longs), shorts=len(shorts))
    (CLIPS / "journey.json").write_text(json.dumps(told, indent=1) + "\n", encoding="utf-8")


# The final book's submission folder at $10M, where the films read from.
def final_pack() -> Path:
    return Path("out") / "finals" / final_run(1e7) / "submission"


# Growth of $1 after costs: final book vs cash plus 4% and the S&P 500.
def growth() -> None:
    book = pd.read_csv(final_pack() / "returns.csv", parse_dates=["holding_month"])
    marks = P.benchmarks().set_index("month").reindex(book["holding_month"])
    lines = [
        ("Final book", (1 + book["portfolio_total_return"]).cumprod(), INK, 3.2, "-"),
        ("S&P 500", (1 + marks["mkt_rf"] + marks["rf"]).cumprod().to_numpy(), BENCH, 1.8, "--"),
        ("Cash plus 4%", (1 + marks["rf"] + 0.04 / 12).cumprod().to_numpy(), MUTED, 1.6, "-"),
    ]
    x = book["holding_month"].map(pd.Timestamp.toordinal).to_numpy(dtype=float)
    top = max(float(np.nanmax(np.asarray(v))) for _, v, *_ in lines)

    # Frame at t: each line draws in, then its end value is labelled.
    def draw(fig, t):
        ax = fig.add_axes((0.09, 0.1, 0.72, 0.85))
        tidy(ax)
        p = ease(t / 3.6)
        for label, values, colour, width, style in lines:
            px, py = partial(x, np.asarray(values, dtype=float), p)
            ax.plot(px, py, color=colour, lw=width, ls=style)
            alpha = ease((t - 3.7) / 0.6)
            if alpha > 0:
                end = float(np.asarray(values)[-1])
                ax.text(
                    x[-1] + 40,
                    end,
                    f"{label}  ${end:.2f}",
                    color=colour,
                    va="center",
                    fontsize=13,
                    weight="bold" if colour == INK else "normal",
                    alpha=alpha,
                )
        ax.set_xlim(x[0], x[-1])
        ax.set_ylim(0.8, top * 1.08)
        years = [pd.Timestamp(f"{y}-01-01").toordinal() for y in range(2021, 2027)]
        ax.set_xticks(years, [str(y) for y in range(2021, 2027)])
        ax.set_ylabel("Growth of $1", color=MUTED)
        ax.axhline(1, color=MUTED, lw=0.6)

    film("growth", (8.3, 5.2), 5.6, draw)


# Rolling 12-month S&P 500 beta inside a true zero-beta book's range.
def beta() -> None:
    book = pd.read_csv(final_pack() / "returns.csv", parse_dates=["holding_month"])
    market = P.benchmarks().set_index("month")["mkt_rf"].reindex(book["holding_month"]).to_numpy()
    net = book["net"].to_numpy()
    rows = []
    for end in range(12, len(net) + 1):
        y, m = net[end - 12 : end], market[end - 12 : end]
        slope = np.cov(y, m)[0, 1] / np.var(m, ddof=1)
        band = 1.96 * np.std(y, ddof=1) / (np.std(m, ddof=1) * np.sqrt(11))
        rows.append((book["holding_month"].iloc[end - 1].toordinal(), slope, band))
    x, b, band = (np.array(c, dtype=float) for c in zip(*rows))

    # Frame at t: the zero-beta band shades in, then the beta line draws.
    def draw(fig, t):
        ax = fig.add_axes((0.1, 0.1, 0.86, 0.85))
        tidy(ax)
        shade = ease(t / 0.8)
        ax.fill_between(x, -band, band, color="#E3E8ED", alpha=shade, lw=0)
        if shade > 0.5:
            ax.text(
                x[2],
                float(band.max()) * 0.92,
                "Range for a truly zero-beta book, 95%",
                color=MUTED,
                fontsize=12,
                alpha=ease((t - 0.4) / 0.6),
            )
        ax.axhline(0, color=MUTED, lw=0.9)
        px, py = partial(x, b, ease((t - 0.6) / 3.4))
        if len(px) > 1:
            ax.plot(px, py, color=INK, lw=3)
        ax.set_xlim(x[0], x[-1])
        lim = float(band.max()) * 1.15
        ax.set_ylim(-lim, lim)
        years = [pd.Timestamp(f"{y}-01-01").toordinal() for y in range(2022, 2027)]
        ax.set_xticks(years, [str(y) for y in range(2022, 2027)])
        ax.set_ylabel("Beta, rolling 12 months", color=MUTED)

    film("beta", (8.3, 5.2), 5.0, draw)


# 1,000 random large-cap books pile up; the final book lands far right.
def null() -> None:
    folder = ARCHIVE / "final_exhibits"
    irs = pd.read_csv(folder / "null_irs.csv")["ir"].to_numpy()
    ours = load(folder / "report.json")["null"]["final_ir"]
    width = 0.05
    column = np.floor(irs / width)
    rng = np.random.default_rng(5)
    start = rng.uniform(0, 2.2, len(irs))
    height = np.zeros(len(irs))
    for c in np.unique(column):
        members = np.flatnonzero(column == c)
        height[members[np.argsort(start[members])]] = np.arange(len(members)) + 0.5
    x = (column + 0.5) * width
    tallest = height.max() + 0.5
    lo, hi = float(irs.min()) - 0.3, max(ours, 0.0) + 0.6

    # Frame at t: random books fall into their pile, then ours lands.
    def draw(fig, t):
        ax = fig.add_axes((0.06, 0.15, 0.9, 0.8))
        tidy(ax)
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, tallest * 1.3)
        box = ax.get_window_extent()
        across = box.width * 72 / fig.dpi / (hi - lo) * width
        down = box.height * 72 / fig.dpi / (tallest * 1.3)
        dot = 0.92 * min(across, down)
        fall = np.clip((t - start) / 0.55, 0, 1) ** 2
        seen = t >= start
        y = tallest * 1.3 + (height - tallest * 1.3) * fall
        ax.scatter(x[seen], y[seen], s=dot**2, color=ALT, linewidths=0)
        ax.axvline(0, color=MUTED, lw=0.8)
        a = ease((t - 2.6) / 0.6)
        if a > 0:
            ax.text(
                float(np.median(irs)),
                tallest * 1.08,
                f"{len(irs):,} random books",
                ha="center",
                color=ALT,
                fontsize=15,
                alpha=a,
            )
        land = np.clip((t - 3.0) / 0.6, 0, 1) ** 2
        if t >= 3.0:
            ax.scatter(
                [ours],
                [tallest * 1.3 * (1 - land) + 0.5 * land],
                s=(dot * 3.2) ** 2,
                color=INK,
                zorder=5,
            )
        ring = ease((t - 3.6) / 0.8)
        if 0 < ring < 1:
            ax.scatter(
                [ours],
                [0.5],
                s=(dot * (3.2 + 9 * ring)) ** 2,
                facecolors="none",
                edgecolors=INK,
                linewidths=2,
                alpha=1 - ring,
                zorder=4,
            )
        b = ease((t - 3.8) / 0.5)
        if b > 0:
            ax.text(
                ours,
                tallest * 0.42,
                f"Final book\n{ours:.2f}",
                ha="center",
                color=INK,
                fontsize=16,
                weight="bold",
                alpha=b,
            )
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.grid(False)
        ax.set_xlabel("IR against cash plus 4%, 2021 to August 2026, after costs", color=MUTED)

    film("null", (8.3, 4.9), 5.6, draw)


# Dollars a year and IR by fund size, each book's line from $1M to $5B.
def capacity() -> None:
    books = load(ARCHIVE / "capacity.json").get("books", {})
    lines = []
    for name, (colour, label) in BOOKS.items():
        rows = books.get(name, {}).get("record", [])
        if rows:
            caps = np.log10([r["capital"] for r in rows])
            dollars = np.array([r["dollars"] / 1e6 for r in rows])
            ir = np.array([r["information_ratio"] for r in rows])
            lines.append((label, colour, caps, dollars, ir))
    sizes = ["$1M", "$10M", "$100M", "", "$1B", "$5B"]
    ticks = np.log10(CAPITALS)

    # Frame at t: dollars on the left and IR on the right draw in together.
    def draw(fig, t):
        left, right = fig.add_axes((0.06, 0.16, 0.4, 0.74)), fig.add_axes((0.56, 0.16, 0.4, 0.74))
        p = ease(t / 3.4)
        for label, colour, caps, dollars, ir in lines:
            heavy = colour == INK
            for ax, values in (
                (left, np.sign(dollars) * np.log10(1 + np.abs(dollars))),
                (right, ir),
            ):
                px, py = partial(caps, values, p)
                ax.plot(
                    px,
                    py,
                    color=colour,
                    lw=3.2 if heavy else 1.8,
                    marker="o",
                    markersize=6 if heavy else 4,
                    label=label if ax is left else None,
                )
        for ax, title in (
            (left, "Dollars a year over cash, $M"),
            (right, "IR against cash plus 4%"),
        ):
            tidy(ax)
            ax.axhline(0, color=MUTED, lw=0.8)
            ax.set_xticks(ticks, sizes)
            ax.set_xlim(ticks[0] - 0.15, ticks[-1] + 0.15)
            ax.set_title(title, color=INK, loc="left", fontsize=15)
        marks = [-1000, -100, -10, 0, 10, 100, 1000]
        left.set_yticks(
            [np.sign(v) * np.log10(1 + abs(v)) for v in marks], [f"{v:,}" for v in marks]
        )
        values = np.concatenate([line[4] for line in lines])
        right.set_ylim(min(values.min(), 0) - 0.2, values.max() + 0.3)
        left.legend(frameon=False, loc="lower left", fontsize=11, ncol=2)

    film("capacity", (12.1, 3.6), 5.0, draw)


# Our longs as 100 dots: chance ringed, real crowd favourites in gold.
def overlap() -> None:
    run = final_run(1e7)
    share = load(ARCHIVE / "crowd_insights.json")[f"book {run}"]["overlap"]["retail"]
    gold = int(round(share["longs_in_favourites"] * 100))
    rng = np.random.default_rng(11)
    order = rng.permutation(100)
    chance, liked = order[:10], order[:gold]
    col, row = np.arange(100) % 20, np.arange(100) // 20
    xy = np.column_stack([col * 0.56, (4 - row) * 0.56])
    delay = rng.uniform(0, 0.8, 100)

    # Frame at t: dots appear, chance is ringed, then favourites turn gold.
    def draw(fig, t):
        ax = fig.add_axes((0.02, 0.06, 0.96, 0.88))
        ax.set_xlim(-0.5, 18.2)
        ax.set_ylim(-0.4, 2.65)
        ax.set_aspect("equal")
        ax.axis("off")
        appear = ease((t - delay) / 0.4)
        ax.scatter(xy[:, 0], xy[:, 1], s=430 * appear, color="#D5DCE3", linewidths=0)
        ring = ease((t - 1.5) / 0.5)
        if ring > 0:
            ax.scatter(
                xy[chance, 0],
                xy[chance, 1],
                s=860,
                facecolors="none",
                edgecolors=MUTED,
                linewidths=1.8,
                linestyle="--",
                alpha=ring,
            )
        fill = ease((t - 2.8 - delay[liked] * 0.6) / 0.4)
        ax.scatter(
            xy[liked, 0],
            xy[liked, 1],
            s=430 * (1 + 0.25 * np.sin(np.pi * fill)),
            color=SUN,
            alpha=fill,
            linewidths=0,
            zorder=3,
        )
        a, b = ease((t - 1.8) / 0.5), ease((t - 3.4) / 0.5)
        ax.text(11.6, 1.75, "Chance would give 10", color=MUTED, fontsize=21, alpha=a)
        ax.text(
            11.6,
            0.95,
            f"AI crowd favourites {gold}",
            color=GOLD,
            fontsize=24,
            weight="bold",
            alpha=b,
        )
        ax.text(
            11.6,
            0.2,
            "Of every 100 of our longs",
            color=MUTED,
            fontsize=16,
            alpha=ease((t - 0.6) / 0.5),
        )

    film("overlap", (12.1, 3.4), 5.0, draw)


# Six AI colleagues around the PM fly out and report back; none trades.
def desk() -> None:
    roles = [
        ("Rules reader", "Quotes every limit"),
        ("Triage", "Sorts company filings"),
        ("Analyst", "Reads a stock's month"),
        ("Devil's advocate", "Attacks the book"),
        ("Memo writer", "Checks every number"),
        ("Explainer", "Says why we held a name"),
    ]
    tones = ["#5CC8E0", "#7FD1AE", "#F2C14E", "#E07A3F", "#C792EA", "#8AB4F8"]
    angle = np.pi / 2 + np.arange(6) * np.pi / 3 + np.pi / 6
    home = np.column_stack([8 + 5.6 * np.cos(angle), 3.0 + 2.05 * np.sin(angle)])

    # Frame at t: colleagues fly out, are named, then send findings back.
    def draw(fig, t):
        ax = fig.add_axes((0, 0, 1, 1))
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 6.1)
        ax.set_aspect("equal")
        ax.axis("off")
        for i, ((name, role), tone) in enumerate(zip(roles, tones)):
            go = ease((t - 0.7 - 0.25 * i) / 0.9)
            if go <= 0:
                continue
            x, y = 8 + (home[i, 0] - 8) * go, 3.0 + (home[i, 1] - 3.0) * go
            ax.plot([8, x], [3.0, y], color="#C9D3DC", lw=2, zorder=1)
            flow = (t - 3.2 - 0.3 * i) % 1.6 / 1.6
            if t > 3.2 + 0.3 * i:
                px, py = x + (8 - x) * flow, y + (3.0 - y) * flow
                ax.scatter([px], [py], s=70, color=tone, zorder=2, alpha=1 - 0.6 * flow)
            ax.scatter([x], [y], s=1500, color=tone, zorder=3, linewidths=0)
            a = ease((t - 1.3 - 0.25 * i) / 0.5)
            below = y < 2.9
            ax.text(
                x,
                y + (-0.62 if below else 0.5),
                name,
                ha="center",
                fontsize=17,
                weight="bold",
                color=INK,
                alpha=a,
            )
            ax.text(
                x,
                y + (-0.98 if below else 0.88),
                role,
                ha="center",
                fontsize=14,
                color=MUTED,
                alpha=a,
            )
        boss = ease(t / 0.5)
        ax.scatter([8], [3.0], s=4800 * boss, color="#0F5C7A", zorder=4, linewidths=0)
        ax.text(
            8,
            3.0,
            "Portfolio\nmanager",
            ha="center",
            va="center",
            fontsize=16,
            weight="bold",
            color=WHITE,
            alpha=ease((t - 0.3) / 0.4),
            zorder=5,
        )

    film("desk", (12.1, 4.6), 6.0, draw)


# Every benchmark on the same money, each bar in turn, final book last.
def ladder() -> None:
    from fiam.report.figures import ladder_rows

    rows = ladder_rows()
    lo = min(0.0, min(r[1] for r in rows)) - 0.35
    hi = max(r[1] for r in rows) + 0.35

    # Frame at t: each benchmark's label and bar grow in, one after another.
    def draw(fig, t):
        ax = fig.add_axes((0.37, 0.12, 0.6, 0.84))
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.set_xlim(lo, hi)
        ax.set_ylim(-0.6, len(rows) - 0.4)
        ax.axvline(0, color=MUTED, lw=0.8)
        for i, (label, value, colour) in enumerate(rows):
            grow = ease((t - 0.3 - 0.42 * i) / 0.6)
            heavy = i == len(rows) - 1
            ax.barh(i, value * grow, 0.66, color=colour)
            ax.text(
                lo - 0.05,
                i,
                label,
                ha="right",
                va="center",
                fontsize=14 if heavy else 13,
                weight="bold" if heavy else "normal",
                color=INK,
                alpha=ease((t - 0.1 - 0.42 * i) / 0.4),
            )
            if grow >= 1:
                off = 0.04 if value >= 0 else -0.04
                ax.text(
                    value + off,
                    i,
                    f"{value:.2f}",
                    va="center",
                    fontsize=14,
                    ha="left" if value >= 0 else "right",
                    color=INK,
                    weight="bold" if heavy else "normal",
                )
        ax.set_yticks([])
        ax.set_xlabel("IR against cash plus 4% at $10M, 2021 to August 2026", color=MUTED)

    film("ladder", (8.4, 4.4), 4.6, draw)


# AI copycats buying our longs, shorting our shorts, vs the chance line.
def copycats() -> None:
    from fiam.report.figures import copycat_test

    test = copycat_test()
    names = {"v1": "our recipe", "brief_2026": "the 2026 brief", "case_2025": "the 2025 case"}
    keys = list(test)
    top = max(t[k] for t in test.values() for k in ("buys_our_longs", "shorts_our_shorts"))

    # Frame at t: the chance line draws, then each recipe's two bars rise.
    def draw(fig, t):
        ax = fig.add_axes((0.09, 0.1, 0.88, 0.78))
        tidy(ax)
        ax.set_ylim(0, top * 1.25)
        ax.set_xlim(-0.6, len(keys) - 0.4)
        line = ease(t / 0.6)
        ax.plot([-0.6, -0.6 + (len(keys) + 0.2) * line], [1, 1], color=MUTED, ls="--", lw=1.4)
        for i, key in enumerate(keys):
            for j, (part, colour) in enumerate(
                (("buys_our_longs", OURS), ("shorts_our_shorts", "#C8501E"))
            ):
                grow = ease((t - 0.8 - 0.35 * i - 0.15 * j) / 0.7)
                value = test[key][part]
                ax.bar(i + (j - 0.5) * 0.38, value * grow, 0.36, color=colour)
                if grow >= 1:
                    ax.text(
                        i + (j - 0.5) * 0.38,
                        value + 0.05,
                        f"{value:.1f}x",
                        ha="center",
                        fontsize=13,
                        color=INK,
                    )
        ax.set_xticks(range(len(keys)), [f"Given {names.get(k, k)}" for k in keys])
        a = ease((t - 0.4) / 0.4)
        fig.text(0.09, 0.93, "Buys our longs", color=OURS, fontsize=14, weight="bold", alpha=a)
        fig.text(
            0.3, 0.93, "Shorts our shorts", color="#C8501E", fontsize=14, weight="bold", alpha=a
        )
        fig.text(0.54, 0.93, "Chance is 1", color=MUTED, fontsize=14, alpha=a)

    film("copycats", (7.6, 5.2), 4.6, draw)


# Makes missing or named films; without ffmpeg the deck shows stills.
def main(names: list[str]) -> None:
    if not shutil.which("ffmpeg"):
        print("clips skipped: ffmpeg is not installed, so the deck shows the still charts")
        return
    from fiam import data

    films = [growth, beta, null, capacity, overlap, desk, ladder, copycats]
    # The journey needs the stock panel; with no data its saved film stays.
    films += [journey] if data.MANIFEST.exists() else []
    for clip in films:
        missing = not (CLIPS / f"{clip.__name__}.mp4").exists()
        if clip.__name__ in names or (not names and missing):
            clip()


if __name__ == "__main__":
    main(sys.argv[1:])
