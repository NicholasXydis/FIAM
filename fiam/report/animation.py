# The AI Crowd Lab as a film: the harness, 60 AI investors, one real month of votes, the herd, our
# book among their favourites, the copycats and the replay checks. Every frame comes from saved
# answers and our own results (docs/protocols/crowd_amendment_1.md item 8); nothing is re-asked.

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.animation import FFMpegWriter  # noqa: E402
from matplotlib.colors import to_rgba, to_rgba_array  # noqa: E402

from fiam import data, v2  # noqa: E402
from fiam.agents import crowd_lab as L  # noqa: E402
from fiam.agents import harness as H  # noqa: E402
from fiam.paths import read_json as load  # noqa: E402

OUT = Path("out") / "figures" / "ai_crowd.mp4"
POSTER = OUT.with_name("ai_crowd_poster.png")
FPS, SECONDS, FLIGHT = 30, 80, 1.2
NAVY, PANEL, WHITE, MUTED = "#0B1F33", "#132B44", "#FFFFFF", "#8A9BB0"
PETROL, LIGHT, GOLD, ORANGE = "#0F5C7A", "#5CC8E0", "#F2C14E", "#E07A3F"
PERSONAS = ["#5CC8E0", "#7FD1AE", "#F2C14E", "#E07A3F", "#C792EA", "#8AB4F8"]
RECIPES = {"v1": GOLD, "brief_2026": "#8AB4F8", "case_2025": "#C792EA"}
ROLES = [
    "Rules reader",
    "Triage",
    "Analyst",
    "Devil's\nadvocate",
    "PM memo",
    "Explainer",
    "AI crowd",
]
# Scene starts in seconds: harness, crowd, votes, herd, our book, copycats, trust, close.
SCENES = dict(harness=5, crowd=13, votes=22, herd=36, book=46, copy=56, trust=64, close=72)
# The talk's cut, about 40 seconds: copycats and trust have slides of their own after the film;
# the set-up runs at double speed, the herd and our book a little slower so every caption reads.
# (film start, film end, speed)
CUT = ((0, 13, 2.0), (13, 36, 1.7), (36, 56, 1.4), (72, 80, 1.2))
SHORT = OUT.with_name("ai_crowd_short.mp4")


def ease(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def fade(t: float, start: float, length: float = 0.8) -> float:
    return float(ease((t - start) / length))


# The book the film shows: final v3 at $10M once it has its crowd results, else v1.
def our_run() -> str:
    final = load(v2.OUT / "evidence.json").get("v3", {}).get("final", {}).get("name")
    run = f"{final}@1e7" if final else ""
    insights = load(v2.OUT / "crowd_insights.json")
    return run if run and f"book {run}" in insights else "v1@1e7"


# Everything the film shows, from saved answers and results: one month, its votes, our book.
def gather() -> dict:
    retail, copy = L.picks("crowdlab_retail"), L.picks("crowdlab_copycat")
    month = max(set(retail["eom"]) & set(copy["eom"]))
    retail, copy = retail[retail["eom"] == month], copy[copy["eom"] == month]
    run = our_run()
    held = data.read(v2.OUT / run / "record" / "holdings.parquet")
    crowd = load(v2.OUT / "crowd_lab.json")
    insights = load(v2.OUT / "crowd_insights.json")
    tests = insights.get(f"book {run}", insights)
    net = insights.get("network", {})
    logs = ("crowdlab_retail", "crowdlab_copycat")
    return dict(
        month=month,
        retail=retail,
        copy=copy,
        stocks=np.array(sorted(set(retail["permno"]) | set(copy["permno"]))),
        book=held[held["eom"] == month].set_index("permno")["weight"],
        groups=dict(zip(net.get("agents", []), net.get("groups", []))),
        voters=crowd.get("retail", {}).get("agreement", {}).get("effective_voters", 30.0),
        beta=crowd.get(f"{run} record", {}).get("crowding_beta", {}),
        checks=crowd.get("retail", {}).get("replay_checks", {}),
        copycat=tests.get("copycat_test", {}).get("v1", {}),
        overlap=tests.get("overlap", {}),
        decisions=sum(sum(1 for _ in (H.RUNS / f"{n}.jsonl").open()) for n in logs),
    )


# Where each agent and each shown stock sits on a 16 x 9 canvas; agents keyed by crowd and id.
def layout(g: dict) -> dict:
    agents, personas = {}, sorted(g["retail"]["persona"].dropna().unique())
    for a, row in g["retail"].drop_duplicates("agent").set_index("agent").iterrows():
        i, j = personas.index(row["persona"]), int(row["info_set"])
        agents[("r", a)] = (0.9 + 0.5 * j, 7.9 - 0.62 * i, PERSONAS[i % len(PERSONAS)])
    for k, (a, row) in enumerate(g["copy"].drop_duplicates("agent").set_index("agent").iterrows()):
        agents[("c", a)] = (12.9 + 0.5 * (k % 5), 7.9 - 0.62 * (k // 5), RECIPES[row["strategy"]])
    n = len(g["stocks"])
    cols = int(np.ceil(np.sqrt(n * 3.2)))
    i = np.arange(n)
    field = np.column_stack([3.4 + 9.2 * (i % cols) / cols, 0.7 + 3.0 * (i // cols) / (n / cols)])
    return dict(agents=agents, personas=personas, field=field, where=dict(zip(g["stocks"], i)))


# Every vote as a particle from its agent to its stock, launched across the votes scene.
def votes(g: dict, lay: dict) -> dict:
    rows = []
    for crowd, frame, col in (
        ("r", g["retail"], "picked"),
        ("c", g["copy"], "picked"),
        ("c", g["copy"], "shorted"),
    ):
        for a, p in frame[frame[col]][["agent", "permno"]].itertuples(index=False):
            rows.append(((crowd, a), lay["where"][p], col == "shorted"))
    start = SCENES["votes"] + 1 + np.random.default_rng(42).uniform(0, 9.5, len(rows))
    stock = np.array([s for _, s, _ in rows])
    short = np.array([s for _, _, s in rows])
    retail = np.array([k[0] == "r" for k, _, _ in rows])
    return dict(
        start=start,
        src=np.array([lay["agents"][k][:2] for k, _, _ in rows]),
        dst=lay["field"][stock],
        stock=stock,
        short=short,
        retail_votes=np.bincount(stock[retail & ~short], minlength=len(g["stocks"])),
    )


# The agents' positions at time t: the retail crowd drifts into its herding groups.
def positions(t: float, g: dict, lay: dict) -> np.ndarray:
    herd = fade(t, SCENES["herd"] + 1, 2.5)
    k = max(g["groups"].values()) if g["groups"] else 1
    out = []
    for (crowd, a), (x, y, _) in lay["agents"].items():
        if crowd == "r" and g["groups"] and herd > 0:
            ang = 2 * np.pi * (g["groups"].get(a, 1) - 1) / k
            gx = 8 + 2.3 * np.cos(ang) + 0.38 * np.cos(a * 2.4)
            gy = 6.5 + 1.25 * np.sin(ang) + 0.38 * np.sin(a * 2.4)
            x, y = x + (gx - x) * herd, y + (gy - y) * herd
        out.append((x, y))
    return np.array(out)


# One frame: the scene's shapes and words at time t.
def draw(ax, t: float, g: dict, lay: dict, vot: dict) -> None:
    ax.clear()
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")

    def say(x, y, text, size=20, color=WHITE, alpha=1.0, weight="normal", ha="center"):
        if alpha > 0.01:
            ax.text(
                x,
                y,
                text,
                color=color,
                fontsize=size,
                alpha=alpha,
                ha=ha,
                va="center",
                weight=weight,
            )

    if t < SCENES["harness"]:
        a = fade(t, 0.3) * (1 - fade(t, SCENES["harness"] - 0.8))
        rng = np.random.default_rng(int(t * 4))
        ax.scatter(rng.uniform(0, 16, 140), rng.uniform(0, 9, 140), s=4, color=LIGHT, alpha=0.3 * a)
        say(8, 5.2, "INSIDE AN AI CROWD", 54, WHITE, a, "bold")
        say(
            8,
            4.0,
            f"60 AI investors  ·  19 months  ·  {g['decisions']:,} decisions  ·  $0 API",
            20,
            LIGHT,
            fade(t, 1.2) * a,
        )
        return

    if t < SCENES["crowd"]:
        a = 1 - fade(t, SCENES["crowd"] - 0.8)
        grow = fade(t, SCENES["harness"], 1.2)
        ax.add_patch(plt.Circle((8, 4.8), 1.25 * grow + 1e-3, color=PETROL, alpha=a))
        say(8, 5.0, "OUR HARNESS", 22, WHITE, a * grow, "bold")
        say(8, 4.5, "local GPU · pinned models · replayable", 12, LIGHT, a * grow)
        for k, role in enumerate(ROLES):
            show = fade(t, SCENES["harness"] + 1 + 0.6 * k)
            ang = np.pi / 2 + 2 * np.pi * k / len(ROLES)
            x, y = 8 + 3.4 * np.cos(ang), 4.8 + 2.9 * np.sin(ang)
            ax.plot(
                [8, 8 + (x - 8) * show],
                [4.8, 4.8 + (y - 4.8) * show],
                color=LIGHT,
                alpha=0.5 * a,
                lw=1.5,
            )
            ax.add_patch(
                plt.Circle((x, y), 0.6 * show + 1e-3, color=PANEL, ec=LIGHT, lw=1.5, alpha=a)
            )
            say(x, y, role, 11, WHITE, a * show)
        say(
            8,
            0.6,
            "Every call saved, hashed and replayable.  No agent ever trades our book.",
            15,
            MUTED,
            a * fade(t, SCENES["harness"] + 5.5),
        )
        return

    # The 60 agents: gold copycats alone stay bright while the copycats scene runs.
    pts = positions(t, g, lay)
    colours = to_rgba_array([c for _, _, c in lay["agents"].values()])
    if SCENES["copy"] <= t < SCENES["trust"]:
        mine = np.array([k[0] == "c" and c == GOLD for k, (_, _, c) in lay["agents"].items()])
        colours[:, 3] = np.where(mine, 1.0, 0.18)
    grow = fade(t, SCENES["crowd"], 1.5)
    ax.scatter(pts[:, 0], pts[:, 1], s=150 * grow, c=colours, edgecolors="white", linewidths=0.6)
    if t < SCENES["votes"]:
        say(2.1, 8.6, "30 AI retail investors", 15, WHITE, grow)
        say(13.9, 8.6, "30 AI copycat funds", 15, WHITE, grow)
        for i, p in enumerate(lay["personas"]):
            say(0.5, 7.9 - 0.62 * i, p, 10, PERSONAS[i % len(PERSONAS)], grow, ha="right")
        for k, (name, c) in enumerate(RECIPES.items()):
            say(15.5, 7.6 - 1.24 * k, name.replace("_", " "), 10, c, grow, ha="left")
        say(8, 2.2, "6 personas × 5 information sets", 18, LIGHT, fade(t, SCENES["crowd"] + 2))
        say(8, 1.4, "3 strategy recipes × 10 funds", 18, LIGHT, fade(t, SCENES["crowd"] + 3))
        return

    # The stock field: each stock brightens as votes land on it; gold marks the crowd's favourites.
    landed = vot["start"] + FLIGHT <= t
    count = np.bincount(vot["stock"][landed & ~vot["short"]], minlength=len(lay["field"]))
    glow = count / max(count.max(), 1)
    cols = np.where(glow[:, None] > 0, to_rgba_array([LIGHT]), to_rgba_array([MUTED]))
    cols[:, 3] = 0.25 + 0.75 * glow
    sizes = 5 + 40 * glow
    fav = vot["retail_votes"] >= np.quantile(vot["retail_votes"][vot["retail_votes"] > 0], 0.9)
    if t >= SCENES["book"]:
        cols[fav] = to_rgba(GOLD)
        sizes = np.where(fav, 40, sizes)
    ax.scatter(lay["field"][:, 0], lay["field"][:, 1], s=sizes, c=cols, linewidths=0)
    flying = (vot["start"] <= t) & (t < vot["start"] + FLIGHT)
    if flying.any():
        k = ease((t - vot["start"][flying]) / FLIGHT)[:, None]
        pos = vot["src"][flying] + (vot["dst"][flying] - vot["src"][flying]) * k
        ax.scatter(
            pos[:, 0],
            pos[:, 1],
            s=10,
            c=np.where(vot["short"][flying], ORANGE, GOLD),
            alpha=0.85,
            linewidths=0,
        )

    if t < SCENES["herd"]:
        say(
            8,
            4.35,
            f"One month of real votes, {g['month']:%B %Y}",
            20,
            WHITE,
            fade(t, SCENES["votes"]),
        )
        say(
            8,
            3.95,
            "9 anonymous cards of 40 stocks each  ·  8 picks per card",
            13,
            MUTED,
            fade(t, SCENES["votes"] + 1),
        )
        say(8, 0.25, f"{int(landed.sum()):,} votes landed", 13, LIGHT, fade(t, SCENES["votes"] + 2))
    elif t < SCENES["book"]:
        n = 30 - (30 - g["voters"]) * fade(t, SCENES["herd"] + 1, 4)
        say(
            8,
            4.35,
            f"30 AI investors vote like {n:.1f} independent ones",
            24,
            WHITE,
            fade(t, SCENES["herd"]),
            "bold",
        )
    elif t < SCENES["copy"]:
        longs = [lay["where"][p] for p in g["book"][g["book"] > 0].index if p in lay["where"]]
        shorts = [lay["where"][p] for p in g["book"][g["book"] < 0].index if p in lay["where"]]
        ring = fade(t, SCENES["book"] + 1.5)
        for picked, colour in ((longs, LIGHT), (shorts, ORANGE)):
            if picked:
                ax.scatter(
                    *lay["field"][picked].T,
                    s=90,
                    facecolors="none",
                    edgecolors=colour,
                    linewidths=1.6,
                    alpha=ring,
                )
        say(
            8,
            4.35,
            "Gold marks the AI crowd's favourites. Rings mark our longs and shorts.",
            18,
            WHITE,
            fade(t, SCENES["book"]),
        )
        share = g["overlap"]
        if share:
            say(
                8,
                3.95,
                f"Over 19 months, {share['retail']['longs_in_favourites']:.0%} of our longs are AI "
                f"retail favourites and {share['copycat']['longs_in_favourites']:.0%} copycat "
                "ones, against 10% by chance",
                17,
                GOLD,
                fade(t, SCENES["book"] + 3),
            )
        if g["beta"]:
            say(
                8,
                0.25,
                f"Our returns load {g['beta'].get('beta', 0):.2f} on the AI crowd's "
                f"favourites, t-stat {g['beta'].get('t', 0):.1f}",
                14,
                LIGHT,
                fade(t, SCENES["book"] + 5),
            )
    elif t < SCENES["trust"]:
        say(
            8,
            4.35,
            "The copycats given our own one-paragraph recipe",
            20,
            GOLD,
            fade(t, SCENES["copy"]),
        )
        c = g["copycat"]
        if c:
            say(
                8,
                3.95,
                f"Buy our longs {c['buys_our_longs']:.1f}× as often as chance and short "
                f"our shorts {c['shorts_our_shorts']:.1f}×",
                17,
                WHITE,
                fade(t, SCENES["copy"] + 1.5),
            )
    elif t < SCENES["close"]:
        checks = g["checks"]
        say(
            8,
            4.6,
            "Is the AI reading, or remembering?",
            22,
            WHITE,
            fade(t, SCENES["trust"]),
            "bold",
        )
        if checks.get("rerun"):
            say(
                8,
                4.0,
                f"Same card asked again, {checks['rerun']['agreement']:.0%} identical answers"
                f" across {checks['rerun']['cards']} cards",
                17,
                LIGHT,
                fade(t, SCENES["trust"] + 1.5),
            )
        if checks.get("perturbed"):
            say(
                8,
                3.55,
                f"Numbers on the card nudged, only {checks['perturbed']['agreement']:.0%} "
                "of picks survive",
                17,
                GOLD,
                fade(t, SCENES["trust"] + 3.5),
            )
    else:
        a = fade(t, SCENES["close"])
        ax.add_patch(plt.Rectangle((0, 0), 16, 9, color=NAVY, alpha=0.88 * a))
        say(8, 5.4, "AI CROWD LAB", 46, WHITE, a, "bold")
        say(
            8,
            4.4,
            "The next crowd is made of machines. We built one to see who we trade against.",
            17,
            LIGHT,
            fade(t, SCENES["close"] + 1),
        )
        say(
            8,
            3.6,
            "Every decision replayable  ·  $0 API  ·  No agent ever trades our book",
            15,
            MUTED,
            fade(t, SCENES["close"] + 2.5),
        )


# The film time shown on each frame of the talk's cut.
def cut() -> np.ndarray:
    return np.concatenate([np.arange(a, b, speed / FPS) for a, b, speed in CUT])


# The full film, the talk's cut and the poster, from one gathering of the saved answers.
def main(seconds: float = SECONDS) -> None:
    plt.rcParams["font.family"] = ["Calibri", "DejaVu Sans"]
    g = gather()
    lay = layout(g)
    vot = votes(g, lay)
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=NAVY)
    ax = fig.add_axes((0, 0, 1, 1), facecolor=NAVY)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for target, times in ((OUT, np.arange(int(FPS * seconds)) / FPS), (SHORT, cut())):
        # Quality-led H.264 that any laptop's PowerPoint plays smoothly, and starts at once.
        quality = [
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            "-preset",
            "slow",
            "-movflags",
            "+faststart",
        ]
        writer = FFMpegWriter(fps=FPS, codec="libx264", extra_args=quality)
        with writer.saving(fig, str(target), dpi=120):
            for t in times:
                draw(ax, t, g, lay, vot)
                ax.set_facecolor(NAVY)
                writer.grab_frame(facecolor=NAVY)
        print(f"wrote {target} ({len(times) / FPS:.0f} s, {target.stat().st_size / 1e6:.1f} MB)")
    draw(ax, SCENES["book"] + 7, g, lay, vot)
    ax.set_facecolor(NAVY)
    fig.savefig(POSTER, dpi=120, facecolor=NAVY)


if __name__ == "__main__":
    import sys

    main(float(sys.argv[1]) if sys.argv[1:] else SECONDS)
