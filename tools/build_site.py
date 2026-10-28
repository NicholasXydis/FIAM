# Site data and the ad's crises from the final fund's pick. Read only.

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# The repo root on the path, so crisis windows import fiam from any cwd.
sys.path.insert(0, str(ROOT))
# The site's two data files and the agents' model names.
OUT = ROOT / "site" / "src" / "data" / "fiam.json"
CRASHES = ROOT / "site" / "src" / "data" / "crashes.json"
MODELS = {"gemma": "Gemma 4 26B-A4B", "qwen": "Qwen3.8-27B"}
# The headline's pick files and the hurdle's yearly premium.
V4 = ROOT / "out" / "vfinal" / "final"
PREMIUM = 0.04
# The AI desk's two tests, the eight ideas' gates and the X-ray.
DESK = {
    "early": ROOT / "out" / "vfinal" / "desk" / "decide_ce5cbff850d2.json",
    "late": ROOT / "out" / "vfinal" / "desk" / "final_decide_512e4bdd3a5e.json",
}
GATES = ROOT / "out" / "vfinal" / "gates" / "late_db36eb4b849a.json"
XRAY = ROOT / "out" / "alt" / "xray" / "xray_2026-08-31.json"
# The first strategy's commit, run once on 2021-2026, then revised.
FIRST = "512e4bdd3a5e"
# The organisers' panel, read only for its stocks per month.
PANEL = ROOT / "data" / "organisers" / "chars_final_with_names.parquet"
# The forecasts' months the universe average counts from.
UNIVERSE_FROM = "2020-12-31"
# The ten SYY-10 parts of fiam/vfinal/signals/syy.py, by question.
SIGNALS_FINAL = [
    ("gp_at", +1, "profitable", "Gross profit to assets"),
    ("niq_at", +1, "profitable", "Return on assets"),
    ("ret_12_1", +1, "rising", "12-month momentum"),
    ("chcsho_12m", -1, "careful", "Net stock issues"),
    ("eqnetis_at", -1, "careful", "Net equity issuance"),
    ("at_gr1", -1, "careful", "Asset growth"),
    ("ppeinv_gr1a", -1, "careful", "Investment growth"),
    ("o_score", -1, "safe", "Distress risk (O-score)"),
    ("oaccruals_at", -1, "real", "Operating accruals"),
    ("noa_at", -1, "real", "Net operating assets"),
]
FAMILIES_FINAL = {
    "profitable": "Is it profitable?",
    "rising": "Is it rising?",
    "careful": "Is it careful with its money?",
    "safe": "Is it safe?",
    "real": "Are its profits real?",
}
# Each what-if in plain words; one not listed here stops the build.
WHATIFS = {
    "styles_free": "Style limits lifted",
    "names_220": "At most 220 names",
    "vol_reliability": "Alpha scaled by past reliability",
    "yearly_refits": "Yearly refits",
    "budget_none": "No cost budget",
    "sectors_wide": "Sector limits doubled",
    "speed_0.5": "Trading half way to target",
    "names_480": "At most 480 names",
    "lambda_half": "Half the risk aversion",
    "budget_half": "Half the cost budget",
    "cap_3bn": "Only stocks of $3bn and up",
    "speed_0.2": "Trading a fifth of the way",
}
# The words every what-if's label file must carry.
IN_SAMPLE = "chosen with 2021-2026 visible"
# Exhibit 1's daily S&P 500 path, and the 60/40 steps from the deck.
EXHIBIT_1 = ROOT / "out" / "vfinal" / "exhibits_revised" / "exhibit_1_active_return.csv"
SIXTY_FORTY = ROOT / "out" / "deck" / "sixty_forty_steps.json"
# The comparison file's rows for volatility, and its S&P 500 column.
VOLATILITY = "Annual volatility (%)"
SP500 = "sp500_price"
# Site keys the final fund no longer fills, dropped from the base.
DROPPED = ("capacity", "explained", "factor_story")
# Days in the rolling beta's window.
BETA_DAYS = 252
# Row 21 books fees, spread and impact as one, put under this part.
TRADING_PART = "trading"
# Each year's cards and the monthly column each compounds.
YEAR_COLUMNS = {"strategy": "ret", "benchmark": "hurdle", "market": "market"}
# The comparison file's row for the fund's correlation with the market.
CORRELATION = "Correlation with the market"
# A signed decimal number inside a table cell.
NUMBER = r"[-+]?\d+(?:\.\d+)?"


# A JSON file, as a dict.
def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# A CSV file as one dict per row.
def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# Rounds a number for the site file, so the bundle stays small.
def r(x: float, digits: int = 4) -> float:
    return round(float(x), digits)


# The crises file a pick's headline folder holds, or None if unnamed.
def crises_file(pick: Path) -> Path | None:
    headline = load(pick).get("headline")
    if not headline:
        return None
    commit = pick.stem.removeprefix("pick_")
    return pick.parent / Path(headline).name / f"crises_{commit}.json"


# The newest pick, by when it is last written, whose crises file exists.
def newest_pick(folder: Path = V4) -> Path:
    picks = sorted(folder.glob("pick_*.json"), key=lambda p: p.stat().st_mtime)
    if not picks:
        raise SystemExit(f"No pick file in {folder}: run uv run fiam stage pick first.")
    ready = [p for p in picks if (c := crises_file(p)) is not None and c.exists()]
    if not ready:
        raise SystemExit(f"No pick in {folder} has its crises file: run its crises replay first.")
    return ready[-1]


# The headline folder and its commit from a pick, refused unless final.
def headline_folder(pick: Path) -> tuple[Path, str]:
    got = load(pick)
    if got.get("final") is not True:
        todo = ", ".join(got.get("next", [])) or "none listed"
        raise SystemExit(f"{pick.name} is not final, so no headline yet. Still to run: {todo}.")
    # The folder sits beside its pick, wherever the pick lives.
    return pick.parent / Path(got["headline"]).name, pick.stem.removeprefix("pick_")


# The headline folder's five files, refused if any is missing.
def v4_files(folder: Path, commit: str) -> dict[str, Path]:
    files = {
        "table": folder / f"table_9_1_{commit}.csv",
        "vs_market": folder / f"vs_market_{commit}.csv",
        "daily": folder / f"daily_7_{commit}.parquet",
        "positions": folder / f"positions_7_{commit}.parquet",
        "names": folder / f"arcana_weights_monthly_{commit}_own.csv",
    }
    missing = [p.name for p in files.values() if not p.exists()]
    if missing:
        raise SystemExit(f"{folder} lacks {', '.join(missing)}.")
    return files


# Every number in a table cell, in order.
def numbers(cell: str) -> list[float]:
    return [float(x) for x in re.findall(NUMBER, cell)]


# A cell's first number, as -1.39 in "-1.39 (0.44); at 100% gross".
def first(cell: str) -> float:
    got = numbers(cell)
    if not got:
        raise ValueError(f"no number in {cell!r}")
    return got[0]


# A "value (s.e.)" cell as its value and standard error.
def with_se(cell: str) -> tuple[float, float]:
    got = re.match(rf"\s*({NUMBER})\s*\(({NUMBER})\)", cell)
    if not got:
        raise ValueError(f"no value and s.e. in {cell!r}")
    return float(got[1]), float(got[2])


# The number after a word, as CAGR in "arithmetic -3.57, CAGR -3.80".
def labelled(cell: str, label: str) -> float:
    got = re.search(rf"\b{re.escape(label)}\s+({NUMBER})", cell)
    if not got:
        raise ValueError(f"no {label} in {cell!r}")
    return float(got[1])


# The 23-row table as each row's cells, keyed by row number.
def table_rows(path: Path) -> dict[int, dict]:
    return {int(x["row"]): x for x in rows(path)}


# The fund's column of the comparison with the market, by measure.
def vs_market(path: Path) -> dict[str, float]:
    return {x["measure"]: float(x["fund"]) for x in rows(path)}


# Yearly return over the hurdle before rounding, from row 3's means.
def active_annual(t: dict[int, dict]) -> float:
    fund = labelled(t[3]["strategy"], "arithmetic")
    return (fund - labelled(t[3]["benchmark"], "arithmetic")) / 100


# Trading and borrow costs a year as fractions, rows 21 and 22.
def cost_parts(t: dict[int, dict]) -> tuple[float, float]:
    return float(t[21]["strategy"]) / 100, float(t[22]["strategy"]) / 100


# The month's bill as TB3MS / 1200, its first daily rate x 252 / 12.
def monthly_bill(rf_daily: pd.Series) -> pd.Series:
    month = pd.DatetimeIndex(rf_daily.index).to_period("M")
    return (rf_daily * 252 / 12).groupby(month).first()


# Each month's fund return, bill and hurdle, the endowment row dropped.
def fund_months(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.iloc[1:]
    month = pd.DatetimeIndex(d.index).to_period("M")
    bill = monthly_bill(d["rf"])
    ret = (1 + d["ret"]).groupby(month).prod() - 1
    return pd.DataFrame({"ret": ret, "bill": bill, "hurdle": bill + PREMIUM / 12})


# The S&P 500's daily closes from the benchmarks file, blanks dropped.
def sp500() -> pd.Series:
    close = {
        x["observation_date"]: float(x["SP500"])
        for x in rows(ROOT / "data" / "benchmarks" / "SP500.csv")
        if x["SP500"] not in ("", ".")
    }
    out = pd.Series(close, dtype=float)
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


# The S&P 500's return in each month, last close to last close.
def market_months(close: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    last = close.groupby(pd.DatetimeIndex(close.index).to_period("M")).last()
    got = (last / last.shift(1) - 1).reindex(months)
    if got.isna().any():
        raise SystemExit("The S&P 500 series misses a month of the run.")
    return got


# Growth of $1 a month at a time, starting at 1.
def growth(monthly: pd.Series) -> list[float]:
    return [1.0] + [r(x) for x in (1 + monthly).cumprod()]


# $1 in the fund, the hurdle and the S&P 500, and their monthly moves.
def race_v4(m: pd.DataFrame, market: pd.Series) -> dict:
    return dict(
        book=growth(m["ret"]),
        hurdle=growth(m["hurdle"]),
        market=growth(market),
        market_monthly=[r(x) for x in market],
        book_monthly=[r(x) for x in m["ret"]],
    )


# Each calendar year's fund, hurdle and market returns, compounded.
def years_v4(m: pd.DataFrame, market: pd.Series) -> dict:
    both = m.assign(market=market.to_numpy())
    out = {}
    for year, part in both.groupby(both.index.year):
        got = {k: float((1 + part[c]).prod() - 1) for k, c in YEAR_COLUMNS.items()}
        active = got["strategy"] - got["benchmark"]
        out[str(year)] = {k: r(v) for k, v in got.items()} | {
            "active": r(active),
            "months": len(part),
        }
    return out


# The fund's rolling beta to the S&P 500 and a zero-beta noise band.
def rolling_beta(excess: pd.Series, market: pd.Series, days: int = BETA_DAYS) -> pd.DataFrame:
    both = pd.concat({"y": excess, "x": market}, axis=1, join="inner").dropna()
    y, x = both["y"], both["x"]
    beta = y.rolling(days).cov(x) / x.rolling(days).var()
    slope = y.cov(x) / x.var()
    residual = (y - y.mean() - slope * (x - x.mean())).std()
    band = 1.96 * residual / (x.rolling(days).std() * math.sqrt(days - 1))
    return pd.DataFrame({"beta": beta, "band": band}).dropna()


# The fund's beta from its first day to each day, from its tenth on.
def beta_so_far(excess: pd.Series, market: pd.Series, days: int = 10) -> pd.Series:
    both = pd.concat({"y": excess, "x": market}, axis=1, join="inner").dropna()
    y, x = both["y"], both["x"]
    return (y.expanding(days).cov(x) / x.expanding(days).var()).dropna()


# Each month's rolling beta and band, the share outside, and before.
def beta_v4(daily: pd.DataFrame, close: pd.Series) -> dict:
    d = daily.iloc[1:]
    excess, market = d["ret"] - d["rf"], close.pct_change().dropna()
    got = rolling_beta(excess, market)
    ends = got.groupby(pd.DatetimeIndex(got.index).to_period("M")).last()
    outside = float((ends["beta"].abs() > ends["band"]).mean()) if len(ends) else 0.0
    # Months before the first full window show the beta measured so far.
    early = beta_so_far(excess, market)
    early = early.groupby(pd.DatetimeIndex(early.index).to_period("M")).last()
    first = ends.index[0] if len(ends) else None
    return dict(
        rolling={
            str(k): [r(b, 3), r(n, 3)] for k, b, n in zip(ends.index, ends["beta"], ends["band"])
        },
        since={str(k): r(b, 3) for k, b in early.items() if first is None or k < first},
        outside_noise=r(outside, 3),
    )


# The latest ticker and name of each PERMNO in the Arcana weights file.
def names_v4(path: Path) -> dict[int, tuple[str, str]]:
    cols = ["Date", "Ticker", "PERMNO", "Name"]
    own = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)
    own = own.replace("", pd.NA).sort_values("Date", kind="stable")
    last = own.groupby("PERMNO")[["Ticker", "Name"]].last().fillna("")
    return {
        int(p): (str(t).removesuffix(" US Equity"), str(n))
        for p, t, n in zip(last.index, last["Ticker"], last["Name"])
    }


# Each month's book on its last positions date, in 0.001% units.
def holdings_v4(positions: pd.DataFrame, nav: pd.Series, names: dict, months: list[str]) -> dict:
    p = positions.assign(date=pd.to_datetime(positions["date"]))
    p = p[p["value"] != 0]
    month = p["date"].dt.to_period("M").astype(str)
    p = p.assign(month=month)[p["date"] == p["date"].groupby(month).transform("max")]
    p = p.assign(weight=p["value"] / p["date"].map(nav) * 100)
    order = sorted(int(x) for x in p["permno"].unique())
    index = {permno: i for i, permno in enumerate(order)}
    book = []
    for m in months:
        part = p[p["month"] == m].sort_values("permno")
        flat = []
        for permno, weight in zip(part["permno"], part["weight"]):
            flat += [index[int(permno)], int(round(float(weight) * 1000))]
        book.append(flat)
    known = [names.get(permno, ("", "")) for permno in order]
    return dict(ticker=[t for t, _ in known], name=[n.title() for _, n in known], book=book)


# The headline measures from the table, the comparison and the months.
def headline_v4(
    t: dict[int, dict], vs: dict[str, float], m: pd.DataFrame, daily: pd.DataFrame, old: dict
) -> dict:
    alpha, alpha_se = with_se(t[5]["strategy"])
    # The daily beta is the headline one; row 6's monthly sits beside it.
    beta, beta_se = with_se(t[7]["strategy"])
    monthly, monthly_se = with_se(t[6]["strategy"])
    net = active_annual(t) + PREMIUM
    days = daily.iloc[1:]
    best, worst = m["ret"].idxmax(), m["ret"].idxmin()
    return old | dict(
        ir=r(first(t[23]["strategy"]), 3),
        ir_gross=r(float(t[9]["strategy"]), 3),
        net=r(net),
        gross=r(net + sum(cost_parts(t))),
        cagr=r(labelled(t[3]["strategy"], "CAGR") / 100),
        vol=r(float(t[4]["strategy"]) / 100, 5),
        sharpe=r(float(t[8]["strategy"]), 3),
        drawdown=r(float(t[11]["strategy"]) / 100),
        alpha=r(alpha / 100),
        alpha_t=r(alpha / alpha_se, 2),
        beta=r(beta, 3),
        beta_se=r(beta_se, 3),
        beta_monthly=r(monthly, 3),
        beta_monthly_se=r(monthly_se, 3),
        correlation=r(vs[CORRELATION], 3),
        hit=r((m["ret"] > m["hurdle"]).mean(), 3),
        positions=r(labelled(t[14]["strategy"], "avg"), 1),
        longs=r(days["n_long"].mean(), 1),
        shorts=r(days["n_short"].mean(), 1),
        turnover=r(labelled(t[17]["strategy"], "without") / 100 / 12, 3),
        cumulative=r(float(t[2]["strategy"]) / 100),
        best_month=dict(month=str(best), value=r(m["ret"][best])),
        worst_month=dict(month=str(worst), value=r(m["ret"][worst])),
    )


# Return a year before and after the two booked costs, and the hurdle.
def costs_v4(t: dict[int, dict]) -> dict:
    trading, borrow = cost_parts(t)
    net = labelled(t[3]["strategy"], "arithmetic") / 100
    return dict(
        gross=r(net + trading + borrow),
        net=r(net),
        hurdle=r(labelled(t[3]["benchmark"], "arithmetic") / 100),
        parts={TRADING_PART: r(trading, 5), "borrow": r(borrow, 5)},
        total=r(trading + borrow, 5),
        ir_gross=r(float(t[9]["strategy"]), 3),
        turnover=r(labelled(t[17]["strategy"], "build") / 100, 3),
    )


# The site data with its headline keys refilled from a run folder.
def v4(base: dict, folder: Path, commit: str, close: pd.Series) -> dict:
    f = v4_files(folder, commit)
    t, daily = table_rows(f["table"]), pd.read_parquet(f["daily"])
    m = fund_months(daily)
    market = market_months(close, m.index)
    months = [str(p) for p in m.index]
    return base | dict(
        book=folder.name,
        code=commit,
        window=f"{months[0]} to {months[-1]}",
        months=months,
        headline=headline_v4(t, vs_market(f["vs_market"]), m, daily, base["headline"]),
        years=years_v4(m, market),
        race=race_v4(m, market),
        beta=beta_v4(daily, close),
        stocks=holdings_v4(
            pd.read_parquet(f["positions"]), daily["nav"], names_v4(f["names"]), months
        ),
        costs=costs_v4(t),
    )


# A number with a true minus sign, as the site's own copy writes it.
def minus(x: float, digits: int = 2) -> str:
    return f"{'−' if x < 0 else ''}{abs(x):.{digits}f}"


# One real month: all stocks, the forecast universe and the final book.
def journey_v4(forecasts: Path, positions: pd.DataFrame) -> dict:
    eoms = pd.to_datetime(pd.read_parquet(forecasts, columns=["eom"])["eom"])
    per = eoms[eoms >= UNIVERSE_FROM].value_counts().sort_index()
    last = per.index[-1]
    panel = pd.to_datetime(pd.read_parquet(PANEL, columns=["eom"])["eom"])
    p = positions.assign(date=pd.to_datetime(positions["date"]))
    book = p[(p["date"] == p["date"].max()) & (p["value"] != 0)]
    return dict(
        month=f"{last:%B %Y}",
        stocks=int((panel == last).sum()),
        tradeable=int(per.iloc[-1]),
        longs=int((book["value"] > 0).sum()),
        shorts=int((book["value"] < 0).sum()),
        average=r(per.mean(), 1),
    )


# Each replayed crisis with its dates, the market and the final book.
def crises_v4(folder: Path, commit: str) -> list[dict]:
    from fiam.exhibits.stress import CRISES

    replay = load(folder / f"crises_{commit}.json")["crises"]
    if list(replay) != list(CRISES):
        raise SystemExit("The crises file and the stress windows differ.")
    return [
        dict(
            name=name,
            first=first,
            last=last,
            market=r(replay[name]["market"]),
            book=r(replay[name]["loss"]),
            coverage=r(replay[name]["coverage"], 2),
        )
        for name, (first, last) in CRISES.items()
    ]


# Every finished what-if: its label check and its table's measures.
def whatifs(commit: str) -> list[dict]:
    found = {}
    for table in sorted(V4.glob(f"whatif*/*/table_9_1_{commit}.csv")):
        key = table.parent.name
        label = (table.parent / "LABEL.txt").read_text(encoding="utf-8")
        if IN_SAMPLE not in label or key in found:
            raise SystemExit(f"{table.parent} is unlabelled or repeated.")
        if key not in WHATIFS:
            raise SystemExit(f"Name the what-if {key} in WHATIFS first.")
        t = table_rows(table)
        found[key] = dict(
            key=key,
            label=WHATIFS[key],
            ir=r(first(t[23]["strategy"]), 2),
            ir_gross=r(float(t[9]["strategy"]), 2),
            cagr=r(labelled(t[3]["strategy"], "CAGR") / 100),
            drawdown=r(float(t[11]["strategy"]) / 100),
        )
    return sorted(found.values(), key=lambda x: -x["ir"])


# The S&P 500's yearly volatility and worst daily fall, as fractions.
def sp500_v4(vs: Path) -> dict:
    vol = next(float(x[SP500]) for x in rows(vs) if x["measure"] == VOLATILITY)
    level = 1 + pd.read_csv(EXHIBIT_1, usecols=["sp500"])["sp500"] / 100
    return dict(vol=r(vol / 100, 5), drawdown=r((level / level.cummax() - 1).min(), 5))


# 2022 for the S&P 500, bonds, a 60/40 and the fund, and the steps.
def edge_v4(years: dict) -> dict:
    if not SIXTY_FORTY.exists():
        raise SystemExit(f"No {SIXTY_FORTY}: run the deck's 60/40 steps first.")
    got = load(SIXTY_FORTY)
    year = got["year_2022"]
    return dict(
        year_2022=dict(
            sp500=years["2022"]["market"],
            bonds=r(year["bonds"]),
            sixty_forty=r(year["sixty_forty"]),
            fund=years["2022"]["strategy"],
        ),
        steps=got["steps"],
        window=got["window"],
        source=got["source"],
    )


# The AI desk's tests: IR with no AI, the simple rule and the AI.
def desk_v4() -> dict:
    out = {}
    for when, path in DESK.items():
        got = load(path)
        irs = got["irs"]
        out[when] = dict(
            none=r(irs["A0"], 2),
            rule=r(irs["A1"], 2),
            ai=r(irs["A2"], 2),
            random=got["placebo"]["n"],
            memory=got["memory_gate"]["passes"],
        )
    return out


# The base's agents and the risk desk, the eighth, with its tests.
def agents_v4(base: list[dict], desk: dict) -> list[dict]:
    early, late = desk["early"], desk["late"]
    risk = dict(
        key="desk",
        name="Risk desk",
        model=MODELS["gemma"],
        does="Proposes shrinking a position at a risky moment from a card with no name, "
        "ticker or date. A devil's advocate argues back",
        facts=[
            ["Tested against", f"a fixed rule and {late['random']} random desks"],
            ["IR 2017 to 2020", f"{minus(early['ai'])} with AI, {minus(early['none'])} without"],
            [
                "IR 2021 to 2026, first strategy",
                f"{minus(late['ai'])} with AI, {minus(late['none'])} without",
            ],
            ["Result", "No help, so the fund runs without it"],
        ],
    )
    others = [a for a in base if a["key"] != "desk"]
    # The desk goes before the crowd, whose long label then fits.
    at = next((i for i, a in enumerate(others) if a["key"] == "crowd"), len(others))
    return [*others[:at], risk, *others[at:]]


# The final book on its last day, largest first, and the X-ray's read.
def now_v4(stocks: dict, months: list[str]) -> dict:
    flat = stocks["book"][-1]
    book = [[stocks["ticker"][i], stocks["name"][i], w] for i, w in zip(flat[::2], flat[1::2])]
    book.sort(key=lambda x: -x[2])
    x = load(XRAY)
    cover = x["book_coverage"]
    owned = ("card_spend", "foot_traffic", "web_traffic")
    return dict(
        decision=x["meta"]["as_of"],
        month=months[-1],
        book=book,
        xray=dict(
            names=cover["names"],
            owned=max(cover[k]["names"] for k in owned),
            benzinga=cover["benzinga_ever"]["names"],
            benzinga_share=r(cover["benzinga_ever"]["share_of_gross"], 3),
            top=len(x["cards"]),
            keep=sum(c["suggestion"]["action"] == "keep" for c in x["cards"]),
        ),
    )


# Every attempt: both strategies, the eight ideas and the what-ifs.
def honesty_v4(pick: dict, head: dict, rows: list[dict]) -> dict:
    first_ir = first(table_rows(V4 / f"table_9_1_{FIRST}.csv")[23]["strategy"])
    holm = load(GATES)["late"]["holm"]
    passed = sum(g["passes"] for g in holm.values())
    checks = len(pick["ic_2017_2020"]) + len(pick["early_ir"])
    better = sum(x["ir"] > r(head["ir"], 2) for x in rows)
    families = [
        dict(
            what="The first strategy, frozen before any 2021 to 2026 result",
            family="first",
            eligible=True,
            attempts=1,
            verdict=f"Run once on 2021 to 2026, IR {minus(first_ir)} after costs, then revised",
        ),
        dict(
            what="The revised strategy, its refits and limits settled on 2017 to 2020",
            family="revised",
            eligible=True,
            attempts=checks,
            verdict=f"Shipped, {pick['cadence']} refits and {pick['limits']} limits, "
            f"IR {minus(head['ir'])} after costs",
        ),
        dict(
            what="New ideas, each tested against a bar set in advance",
            family="ideas",
            eligible=False,
            attempts=len(holm),
            verdict=f"{passed} of {len(holm)} passed, so the fund runs on the published signals",
        ),
        dict(
            what="What-ifs chosen with 2021 to 2026 visible",
            family="whatifs",
            eligible=False,
            attempts=len(rows),
            verdict=f"Never the headline, {better} of {len(rows)} did better in hindsight",
        ),
    ]
    return dict(
        attempts=sum(f["attempts"] for f in families),
        eligible=sum(f["attempts"] for f in families if f["eligible"]),
        ideas=len(holm),
        ideas_passed=passed,
        whatifs=len(rows),
        families=families,
    )


# The final fund's scenes refilled on top of the headline keys.
def final(data: dict, folder: Path, commit: str, pick: dict) -> dict:
    f = v4_files(folder, commit)
    rows = whatifs(commit)
    desk = desk_v4()
    head = data["headline"] | dict(breaches=load(folder / f"book_{commit}.json")["breach_days"])
    forecasts = V4 / f"forecasts_{pick['cadence']}_{commit}.parquet"
    kept = {k: v for k, v in data.items() if k not in DROPPED}
    return kept | dict(
        headline=head,
        signals=[dict(code=c, sign=s, family=g, label=x) for c, s, g, x in SIGNALS_FINAL],
        families=FAMILIES_FINAL,
        journey=journey_v4(forecasts, pd.read_parquet(f["positions"])),
        edge=edge_v4(data["years"]),
        sp500=sp500_v4(f["vs_market"]),
        crises=crises_v4(folder, commit),
        desk=desk,
        agents=agents_v4(data["agents"], desk),
        september=now_v4(data["stocks"], data["months"]),
        honesty=honesty_v4(pick, head, rows),
    )


# Any pick file and any base site file, else the defaults.
def options(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Writes the site's data files.")
    parser.add_argument("--pick", type=Path, help="this pick file, not the newest ready one")
    parser.add_argument("--base", type=Path, help="refill this site file, not the bundled one")
    return parser.parse_args(args)


# The final fund refills a base site file, the bundled one by default.
def main(args: list[str]) -> None:
    opts = options(args)
    pick = opts.pick or newest_pick()
    base = opts.base or OUT
    if not base.exists():
        raise SystemExit(f"No {base}: pass --base with a site data file.")
    folder, commit = headline_folder(pick)
    data = final(v4(load(base), folder, commit, sp500()), folder, commit, load(pick))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for out, made in ((OUT, data), (CRASHES, data["crises"])):
        out.write_text(json.dumps(made, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}: {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main(sys.argv[1:])
