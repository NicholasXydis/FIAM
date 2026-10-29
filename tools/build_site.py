# Site data and the film's crises from the fund's pack. Read only.

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# The site's two data files, and the film's own small data file.
OUT = ROOT / "site" / "src" / "data" / "fiam.json"
CRASHES = ROOT / "site" / "src" / "data" / "crashes.json"
FILM = ROOT / "site" / "src" / "film" / "data.json"
# The numbers and charts pack, the one source for every site number.
PACK = Path.home() / "FIAM_work" / "vfinal_pack"
# The agents' model names, and the hurdle's yearly premium over bills.
MODELS = {"gemma": "Gemma 4 26B-A4B", "qwen": "Qwen3.8-27B"}
PREMIUM = 0.04
# The organisers' panel, read only for its stocks per month.
PANEL = ROOT / "data" / "organisers" / "chars_final_with_names.parquet"
# The forecasts' months the universe average counts from.
UNIVERSE_FROM = "2020-12-31"
# The crisis replay run as its method is written, with peer fill.
VARIANT = "new_peer_fill"
# Our three signals among the forecast's inputs, in plain words.
OURS = {
    "syy": "SYY-10 mispricing score",
    "sue_forecast": "Earnings surprise forecast",
    "short_ratio": "Short interest",
}
# The organisers' characteristics are shown in this many equal sets.
BUNDLES = 7
# Columns of the features file that are keys, not forecast inputs.
KEYS = ("date", "permno", "exchcd", "me")
# Days in the rolling beta's window.
BETA_DAYS = 252
# Row 21 books fees, spread and impact as one, put under this part.
TRADING_PART = "trading"
# Each year's cards and the monthly column each compounds.
YEAR_COLUMNS = {"strategy": "ret", "benchmark": "hurdle", "market": "market"}
# The 60/40 slider moves up to this many points of bonds into the fund.
SWAP_MAX = 20
# A signed decimal number inside a table cell.
NUMBER = r"[-+]?\d+(?:\.\d+)?"
# Site keys carried over from the base file; the rest are rebuilt.
KEPT = ("crowd", "agents")
# How far a rebuilt number may stray from the pack's before a stop.
TOLERANCE = 5e-4


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


# Stops the build when a rebuilt number strays from the pack's.
def agree(name: str, ours: float, pack: float, tolerance: float = TOLERANCE) -> None:
    if abs(ours - pack) > tolerance:
        raise SystemExit(f"{name}: rebuilt {ours:.6f}, pack {pack:.6f}. Fix before publishing.")


# Every number in a table cell, in order.
def numbers(cell: str) -> list[float]:
    return [float(x) for x in re.findall(NUMBER, cell)]


# The number after a word, as CAGR in "arithmetic 6.86, CAGR 7.00".
def labelled(cell: str, label: str) -> float:
    got = re.search(rf"\b{re.escape(label)}\s+({NUMBER})", cell)
    if not got:
        raise ValueError(f"no {label} in {cell!r}")
    return float(got[1])


# A "value (s.e.)" cell as its value and standard error.
def with_se(cell: str) -> tuple[float, float]:
    got = re.match(rf"\s*({NUMBER})\s*\(({NUMBER})\)", cell)
    if not got:
        raise ValueError(f"no value and s.e. in {cell!r}")
    return float(got[1]), float(got[2])


# The 23-row table as each row's cells, keyed by row number.
def table_rows(path: Path) -> dict[int, dict]:
    return {int(x["row"]): x for x in rows(path)}


# The PDF's monthly bill, TB3MS / 1200, by month.
def bill(pack: Path) -> pd.Series:
    t = pd.read_csv(pack / "src" / "TB3MS.csv", parse_dates=["observation_date"])
    return pd.Series(t["TB3MS"].to_numpy() / 1200, index=t["observation_date"].dt.to_period("M"))


# The S&P 500's daily return as the engine uses it, from the pack.
def market_daily(pack: Path) -> pd.Series:
    d = pd.read_csv(pack / "data" / "daily_paths.csv", parse_dates=["date"], index_col="date")
    return d["sp500_ret"]


# Each month's fund return, bill and hurdle, the endowment row dropped.
def fund_months(daily: pd.DataFrame, bills: pd.Series) -> pd.DataFrame:
    d = daily.iloc[1:]
    month = pd.DatetimeIndex(d.index).to_period("M")
    ret = (1 + d["ret"]).groupby(month).prod() - 1
    b = bills.reindex(ret.index)
    if b.isna().any():
        raise SystemExit("TB3MS misses a month of the run.")
    return pd.DataFrame({"ret": ret, "bill": b, "hurdle": b + PREMIUM / 12})


# The S&P 500's return in each month, compounded from its days.
def market_months(market: pd.Series, months: pd.PeriodIndex) -> pd.Series:
    got = (1 + market).groupby(pd.DatetimeIndex(market.index).to_period("M")).prod() - 1
    got = got.reindex(months)
    if got.isna().any():
        raise SystemExit("The S&P 500 series misses a month of the run.")
    return got


# Growth of $1 a month at a time, starting at 1.
def growth(monthly: pd.Series) -> list[float]:
    return [1.0] + [r(x) for x in (1 + monthly).cumprod()]


# $1 in the fund, the hurdle and the S&P 500, and their monthly moves.
def race(m: pd.DataFrame, market: pd.Series) -> dict:
    return dict(
        book=growth(m["ret"]),
        hurdle=growth(m["hurdle"]),
        market=growth(market),
        market_monthly=[r(x) for x in market],
        book_monthly=[r(x) for x in m["ret"]],
    )


# Each calendar year's fund, hurdle and market returns, compounded.
def years(m: pd.DataFrame, market: pd.Series) -> dict:
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


# The rebuilt years against the pack's calendar years, or a stop.
def check_years(got: dict, pack: Path) -> None:
    for x in rows(pack / "data" / "calendar_years.csv"):
        y = got[x["year"]]
        agree(f"{x['year']} fund", y["strategy"], float(x["fund_after_costs_pct"]) / 100)
        agree(f"{x['year']} hurdle", y["benchmark"], float(x["hurdle_pct"]) / 100)
        agree(f"{x['year']} S&P 500", y["market"], float(x["sp500_pct"]) / 100)


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
def beta_block(daily: pd.DataFrame, market: pd.Series) -> dict:
    d = daily.iloc[1:]
    excess = d["ret"] - d["rf"]
    mkt = market.reindex(d.index) - d["rf"]
    got = rolling_beta(excess, mkt)
    ends = got.groupby(pd.DatetimeIndex(got.index).to_period("M")).last()
    outside = float((ends["beta"].abs() > ends["band"]).mean()) if len(ends) else 0.0
    # Months before the first full window show the beta measured so far.
    early = beta_so_far(excess, mkt)
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
def names(path: Path) -> dict[int, tuple[str, str]]:
    cols = ["Date", "Ticker", "PERMNO", "Name"]
    own = pd.read_csv(path, usecols=cols, dtype=str, keep_default_na=False)
    own = own.replace("", pd.NA).sort_values("Date", kind="stable")
    last = own.groupby("PERMNO")[["Ticker", "Name"]].last().fillna("")
    return {
        int(p): (str(t).removesuffix(" US Equity"), str(n))
        for p, t, n in zip(last.index, last["Ticker"], last["Name"])
    }


# Each month's book on its last positions date, in 0.001% units.
def holdings(positions: pd.DataFrame, nav: pd.Series, known: dict, months: list[str]) -> dict:
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
    found = [known.get(permno, ("", "")) for permno in order]
    return dict(ticker=[t for t, _ in found], name=[n.title() for _, n in found], book=book)


# Months up, the worst 12 months and the market captures, by month.
def monthly(n: dict, m: pd.DataFrame, market: pd.Series) -> dict:
    ret = m["ret"]
    up = int((ret > 0).sum())
    hits = n["hit_rate"]
    agree("months up", up / len(ret), hits["monthly_hit_rate_pct"] / 100)
    if len(ret) != hits["months"]:
        raise SystemExit("The run's months and the pack's disagree.")
    agree("worst month", float(ret.min()), n["headline"]["max_one_month_loss_pct"] / 100)
    # Each run of 12 months compounded, and the worst of them.
    twelve = (1 + ret).rolling(12).apply(np.prod, raw=True) - 1
    fell = market.to_numpy() < 0
    rose = market.to_numpy() > 0
    # Each capture is the fund's mean month over the market's.
    down = float(ret[fell].mean() / market[fell].mean())
    upside = float(ret[rose].mean() / market[rose].mean())
    return dict(
        months_up=up,
        worst_12=dict(month=str(twelve.idxmin()), value=r(twelve.min())),
        down_capture=r(down, 3),
        up_capture=r(upside, 3),
    )


# The headline measures, from the pack's numbers and the daily file.
def headline(n: dict, t: dict[int, dict], daily: pd.DataFrame, m: pd.DataFrame) -> dict:
    h = n["headline"]
    days = daily.iloc[1:]
    best, worst = m["ret"].idxmax(), m["ret"].idxmin()
    beta_m, beta_m_se = with_se(t[6]["strategy"])
    beta_d, beta_d_se = with_se(t[7]["strategy"])
    agree("monthly beta", beta_m, h["beta_monthly"], 1e-3)
    agree("daily beta", beta_d, h["beta_daily"], 1e-3)
    return dict(
        ir=r(h["ir_after_costs"], 3),
        ir_gross=r(h["ir_before_costs"], 3),
        net=r(h["arithmetic_return_pct"] / 100),
        cagr=r(h["cagr_pct"] / 100),
        vol=r(h["vol_monthly_pct"] / 100, 5),
        sharpe=r(h["sharpe_pdf_bill"], 3),
        drawdown=r(h["max_drawdown_pct"] / 100),
        alpha=r(h["alpha_pct"] / 100),
        alpha_t=r(h["alpha_pct"] / h["alpha_se_pct"], 2),
        # The headline beta is the monthly one, row 6; row 7's daily beside.
        beta=r(beta_m, 3),
        beta_se=r(beta_m_se, 3),
        beta_daily=r(beta_d, 3),
        beta_daily_se=r(beta_d_se, 3),
        correlation=r(n["sp500_context"]["correlation_monthly_with_fund"], 3),
        hit=r(n["hit_rate"]["months_beating_hurdle_pct"] / 100, 3),
        positions=r(h["names_avg"], 1),
        longs=r(days["n_long"].mean(), 1),
        shorts=r(days["n_short"].mean(), 1),
        cumulative=r(h["cumulative_return_pct"] / 100),
        ending=r(h["ending_value_bn"], 4),
        hurdle_ending=r(h["hurdle_ending_bn_pdf_bill"], 4),
        best_month=dict(month=str(best), value=r(m["ret"][best])),
        worst_month=dict(month=str(worst), value=r(m["ret"][worst])),
        breaches=int(h["breaches"]),
        sector_max=r(n["sector_net"]["max_abs_net_pct"] / 100, 4),
        rebalances=int(h["rebalances"]),
    )


# Trading and borrow costs a year as fractions, rows 21 and 22.
def cost_parts(t: dict[int, dict]) -> tuple[float, float]:
    return float(t[21]["strategy"]) / 100, float(t[22]["strategy"]) / 100


# Return a year before and after the two booked costs, and the hurdle.
def costs(t: dict[int, dict]) -> dict:
    trading, borrow = cost_parts(t)
    net = labelled(t[3]["strategy"], "arithmetic") / 100
    hurdle = labelled(t[3]["benchmark"], "arithmetic") / 100
    total = trading + borrow
    gross = net + total
    return dict(
        gross=r(gross, 5),
        net=r(net, 5),
        hurdle=r(hurdle, 5),
        # Cash a year is the hurdle less its premium over bills.
        cash=r(hurdle - PREMIUM, 5),
        # The multiple of today's costs at which the fund meets the hurdle.
        break_even=r((gross - hurdle) / total, 3),
        parts={TRADING_PART: r(trading, 5), "borrow": r(borrow, 5)},
        total=r(total, 5),
        ir_gross=r(float(t[9]["strategy"]), 3),
        turnover=r(labelled(t[17]["strategy"], "build") / 100, 3),
    )


# The forecast's inputs: the organisers' sets and our three signals.
def signals(pack: Path) -> tuple[list[dict], dict]:
    cols = pd.read_parquet(pack / "src" / "forecast" / "plus" / "features.parquet").columns
    inputs = [c for c in cols if c not in KEYS]
    theirs = sorted(c for c in inputs if c not in OURS)
    if sorted(c for c in inputs if c in OURS) != sorted(OURS):
        raise SystemExit("The forecast's inputs lack one of our three signals.")
    size = math.ceil(len(theirs) / BUNDLES)
    out = []
    # Each set holds a run of the characteristics in name order.
    for i in range(0, len(theirs), size):
        part = theirs[i : i + size]
        out.append(
            dict(
                code=f"set{i // size + 1}",
                family="theirs",
                label=f"{len(part)} characteristics, {part[0]} to {part[-1]}",
                count=len(part),
            )
        )
    out += [dict(code=c, family="ours", label=label, count=1) for c, label in OURS.items()]
    families = {"theirs": f"The organisers' {len(theirs)} characteristics", "ours": "Our 3 signals"}
    return out, families


# One real month: all stocks, the forecast universe and the final book.
def journey(pack: Path, positions: pd.DataFrame) -> dict:
    fc = pd.read_parquet(pack / "src" / "forecast" / "elasso_rho.parquet", columns=["eom"])
    eoms = pd.to_datetime(fc["eom"])
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


# A Yahoo monthly bar file's adjusted returns over the run's months.
def yahoo(path: Path, months: pd.PeriodIndex) -> pd.Series:
    j = load(path)["chart"]["result"][0]
    ts = pd.to_datetime(j["timestamp"], unit="s").tz_localize("UTC").tz_convert("America/New_York")
    adj = pd.Series(j["indicators"]["adjclose"][0]["adjclose"], index=ts.tz_localize(None))
    adj.index = adj.index.to_period("M")
    adj = adj[~adj.index.duplicated(keep="last")]
    return adj.pct_change().reindex(months)


# A mix's yearly return, volatility and worst month-end fall.
def mix_stats(x: pd.Series) -> dict:
    wealth = (1 + x).cumprod().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[1.0], wealth]))[1:]
    return dict(
        cagr=r(wealth[-1] ** (12 / len(x)) - 1, 5),
        vol=r(x.std(ddof=1) * math.sqrt(12), 5),
        drawdown=r((wealth / peak - 1).min(), 5),
    )


# 2022 for the S&P 500, bonds, a 60/40 and the fund, and the steps.
def edge(pack: Path, m: pd.DataFrame, yrs: dict, six: dict) -> dict:
    stocks = yahoo(pack / "src" / "SPY.json", m.index)
    bonds = yahoo(pack / "src" / "AGG.json", m.index)
    if stocks.isna().any() or bonds.isna().any():
        raise SystemExit("SPY or AGG misses a month of the run.")
    fund = m["ret"]
    steps = []
    # Each step moves one more point of the portfolio from bonds to us.
    for k in range(SWAP_MAX + 1):
        mixed = 0.6 * stocks + (0.4 - k / 100) * bonds + (k / 100) * fund
        steps.append(dict(fund=k) | mix_stats(mixed))
    agree("60/40 CAGR", steps[0]["cagr"], six["mixes"]["60/40"]["cagr_pct"] / 100)
    agree("60/30/10 CAGR", steps[10]["cagr"], six["mixes"]["60/30/10 fund"]["cagr_pct"] / 100)
    agree("60/20/20 vol", steps[20]["vol"], six["mixes"]["60/20/20 fund"]["vol_pct"] / 100)
    in_2022 = slice("2022-01", "2022-12")
    sixty = 0.6 * stocks + 0.4 * bonds
    # 2022 on the 60/40's own basis: SPY and AGG with dividends in.
    year = dict(
        sp500=r((1 + stocks.loc[in_2022]).prod() - 1),
        bonds=r((1 + bonds.loc[in_2022]).prod() - 1),
        sixty_forty=r((1 + sixty.loc[in_2022]).prod() - 1),
        fund=yrs["2022"]["strategy"],
    )
    legs = six["legs_stats"]
    agree("2022 SPY", year["sp500"], legs["stocks"]["year_2022_pct"] / 100)
    agree("2022 AGG", year["bonds"], legs["bonds"]["year_2022_pct"] / 100)
    agree("2022 60/40", year["sixty_forty"], six["mixes"]["60/40"]["year_2022_pct"] / 100)
    return dict(
        year_2022=year,
        steps=steps,
        window="2021-01 to 2026-08, 68 months, rebalanced each month end",
        source="SPDR SPY and iShares AGG adjusted monthly closes, FRED TB3MS",
    )


# Each replayed crisis with its dates, the market and the final book.
def crises(pack: Path, n: dict) -> list[dict]:
    replay = load(pack / "crises.json")[VARIANT]
    out = [
        dict(
            name=c["crisis"],
            first=c["first"],
            last=c["last"],
            market=r(c["market_pct"] / 100),
            book=r(c["book_pct"] / 100),
            coverage=r(c["coverage_pct"] / 100, 2),
        )
        for c in replay["crises"]
    ]
    summary = n["crises"][VARIANT]
    agree(
        "crisis market mean", np.mean([c["market"] for c in out]), summary["market_mean_pct"] / 100
    )
    agree("crisis book mean", np.mean([c["book"] for c in out]), summary["book_mean_pct"] / 100)
    return out


# The agents the slide shows, by the names the findings file uses.
AGENT_NAMES = {
    "rules": "Rules reader",
    "triage": "Triage",
    "analyst": "Analyst",
    "explainer": "Explainer",
    "memo": "Memo writer",
    "advocate": "Devil's advocate",
    "desk": "Risk desk",
    "crowd": "AI crowd",
}
# What three agents do now, where the base's words describe older runs.
DOES = {
    "analyst": "Reads the latest filing of the book's ten largest longs and ten largest shorts",
    "memo": "Writes the August investor letter, and code checks every number in it",
    "desk": "Writes the risk note on the final book, with every number and level set by code",
    "triage": "Labels each 8-K the book's companies filed as good, bad or neutral news",
}
# Facts an agent may keep beside its finding, each with its own file.
STANDING: dict[str, str] = {}


# Each key number checked against the agent's own output file.
def check_found(found: dict, pack: Path) -> None:
    ai = pack / "ai"
    rules = load(ai / "rules" / "rules_check.json")
    want = {"Rules reader": f"{rules['matched']} of {rules['rules_read']}"}
    sides = load(ai / "analyst" / "analyst_final.json")["balance_by_side"]
    support = sum(side["supports"] for side in sides.values())
    want["Analyst"] = f"{support} of {sum(sum(side.values()) for side in sides.values())}"
    want["Explainer"] = f"{len(load(ai / 'explanations.json')['positions'])} positions"
    verdicts = load(ai / "desk" / "critic_final.json")["verdicts"]
    stand = verdicts["stands"] + verdicts["partly stands"]
    want["Devil's advocate"] = f"{stand} of {sum(verdicts.values())}"
    want["Risk desk"] = f"{load(ai / 'desk' / 'risk_note.json')['levels']['watch']} watch"
    rounded = load(ai / "crowd_aug" / "crowd_where_we_sit.json")["round"]
    want["AI crowd"] = f"crowd beta {rounded['beta']}"
    triage = load(ai / "triage" / "triage_final.json")
    want["Triage"] = f"{triage['filings']['labelled']} 8-Ks"
    for name, number in want.items():
        if found[name]["key_number"] != number:
            raise SystemExit(
                f"{name}: findings say {found[name]['key_number']}, its file {number}."
            )
    # Words each finding must carry from its file: shares, percentiles.
    words = {
        "Triage": [f"{round(triage['share_for_our_side'] * 100)}%"],
        "AI crowd": [
            f"AI crowd's {ordinal(rounded['long_pct'])} percentile",
            f"shorts at the {ordinal(rounded['short_pct'])}",
            f"crowd beta {rounded['beta']}",
        ],
    }
    for name, parts in words.items():
        for part in parts:
            if part not in found[name]["finding"]:
                raise SystemExit(f"{name}: the finding lacks {part!r} from its file.")


# The models the live crowd ran on, read from its run manifests.
def crowd_models(pack: Path) -> str:
    runs = load(pack / "ai" / "crowd_aug" / "crowd_where_we_sit.json")["live_run"]["manifests"]
    files = {run["model_file"] for run in runs.values()}
    names = set()
    # Each model file must be one the site can name.
    for file in files:
        if file.lower().startswith("gemma-4-26b-a4b"):
            names.add(MODELS["gemma"])
        else:
            raise SystemExit(f"The crowd ran on {file}, a model the site cannot name.")
    return " and ".join(sorted(names))


# The base's eight agents with each one's finding on the final book.
def agents(base: list[dict], pack: Path) -> list[dict]:
    file = load(pack / "ai" / "agents_found.json")
    found = file["agents"]
    if file["agents_count"] != 8 or len(found) != 8 or len(base) != 8:
        raise SystemExit("The AI desk must have exactly 8 agents.")
    if set(found) != set(AGENT_NAMES.values()) or {a["key"] for a in base} != set(AGENT_NAMES):
        raise SystemExit("The findings and the slide name different agents.")
    # Every agent must have its finding; none may still be pending.
    if file.get("pending") or any(not isinstance(v, dict) for v in found.values()):
        raise SystemExit("An agent's finding is still pending.")
    check_found(found, pack)
    out = []
    for a in base:
        got = found[AGENT_NAMES[a["key"]]]
        a = {k: v for k, v in a.items() if k != "facts" or a["key"] in STANDING}
        # A fact kept beside a finding needs its file in the pack's AI folder.
        if a["key"] in STANDING and not (pack / "ai" / STANDING[a["key"]]).exists():
            raise SystemExit(f"{a['name']}: its older facts have no backing file.")
        a |= dict(
            does=DOES.get(a["key"], a["does"]),
            finding=got["finding"],
            number=got["key_number"],
            date=got["date"],
        )
        # A run on Gemma names that model; the crowd reads its run manifests.
        source = Path(got["source"]).read_text(encoding="utf-8").lower()
        if a["key"] == "crowd":
            a["model"] = crowd_models(pack)
        elif "gemma" in source:
            a["model"] = MODELS["gemma"]
        out.append(a)
    return out


# The one crowd study the site reads, and the hype map.
CROWD = PACK / "ai" / "crowd_aug" / "crowd_where_we_sit.json"
HYPE = PACK.parent / "hype_map" / "results.json"
# Crowd keys measured on older books, never shown for this fund.
STALE = (
    "picks",
    "models",
    "model_agreement",
    "crowd_beta",
    "crowd_t",
    "longs_in_favourites",
    "shorts_in_favourites",
    "copycat_longs",
    "copycat_test",
    "likes",
    "same_information",
    "same_persona",
    "rerun_agreement",
    "correlation",
    "sell_10bn",
    "headline",
    "favourites",
)


# An ordinal in English words' style: 1st, 2nd, 3rd, 11th, 57th.
def ordinal(n: int) -> str:
    end = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{end}"


# The base's crowd, stale numbers gone and the study's rounded ones in.
def crowd(base: dict, path: Path = CROWD) -> dict:
    x = load(path)
    rounded = x["round"]
    if x["herding"]["retail"]["all_months"]["agents"] != base["agents"]:
        raise SystemExit("The herding study and the crowd count differ.")
    # Gold balls: the 68-month average share of our longs in favourites.
    share = x["spliced_retail"]["average"]["long_in_top_decile"]
    out = {k: v for k, v in base.items() if k not in STALE} | dict(
        effective_voters=rounded["voters"],
        lsv=rounded["lsv"],
        beta=rounded["beta"],
        sell_10bn_pct=rounded["sell_10bn_pct"],
        long_pct=rounded["avg_long_pct"],
        short_pct=rounded["avg_short_pct"],
        favourites_pct=round(share * 100),
    )
    if out["favourites_pct"] != round(share * 100) or not 0 <= out["favourites_pct"] <= 100:
        raise SystemExit("The gold balls drift from the crowd study's average.")
    return out


# Card spend of the book's two sides, as totals only, from the hype map.
def hype(path: Path = HYPE) -> dict:
    card = load(path)["card"]
    sides = card["longs_vs_shorts"]
    fav = card["crowd_favourites"]
    return dict(
        long_growth=r(sides["long_wmean"]),
        short_growth=r(sides["short_wmean"]),
        longs=sides["longs"],
        shorts=sides["shorts"],
        favourites=fav["favourites_with_growth"],
        in_hype=fav["in_hype"],
    )


# The final book on its last day, largest first, and the hype check.
def now(stocks: dict, months: list[str], pack: Path) -> dict:
    flat = stocks["book"][-1]
    book = [[stocks["ticker"][i], stocks["name"][i], w] for i, w in zip(flat[::2], flat[1::2])]
    book.sort(key=lambda x: -x[2])
    return dict(month=months[-1], book=book, hype=hype())


# Every site key rebuilt from the pack, on top of the base's crowd.
def build(base: dict, pack: Path) -> dict:
    src = pack / "src" / "bw_fresh_lag"
    n = load(pack / "numbers.json")
    t = table_rows(src / "table_9_1.csv")
    daily = pd.read_parquet(src / "daily.parquet")
    positions = pd.read_parquet(src / "positions.parquet")
    m = fund_months(daily, bill(pack))
    mkt_daily = market_daily(pack)
    market = market_months(mkt_daily, m.index)
    months = [str(p) for p in m.index]
    yrs = years(m, market)
    check_years(yrs, pack)
    head = headline(n, t, daily, m)
    mkt = market_months(market_daily(pack), m.index)
    head |= monthly(n, m, mkt)
    ran = race(m, market)
    agree("ending value", ran["book"][-1], head["ending"])
    agree("hurdle ending", ran["hurdle"][-1], head["hurdle_ending"])
    stocks = holdings(
        positions, daily["nav"], names(src / "arcana_weights_monthly_own.csv"), months
    )
    sig, fams = signals(pack)
    sp = n["sp500_context"]
    return {k: v for k, v in base.items() if k in KEPT} | dict(
        window=f"{months[0]} to {months[-1]}",
        months=months,
        headline=head,
        years=yrs,
        race=ran,
        beta=beta_block(daily, mkt_daily),
        stocks=stocks,
        signals=sig,
        families=fams,
        journey=journey(pack, positions),
        costs=costs(t),
        edge=edge(pack, m, yrs, n["sixty_forty"]),
        sp500=dict(
            vol=r(sp["vol_monthly_pct"] / 100, 5), drawdown=r(sp["max_drawdown_pct"] / 100, 5)
        ),
        crises=crises(pack, n),
        agents=agents(base["agents"], pack),
        crowd=crowd(base["crowd"]),
        september=now(stocks, months, pack),
    )


# The film's Sharpe ratio and monthly beta, from the pack.
def film_numbers(pack: Path) -> dict[str, float]:
    n = load(pack / "numbers.json")
    t = table_rows(pack / "src" / "bw_fresh_lag" / "table_9_1.csv")
    return dict(sharpe=r(n["headline"]["sharpe_pdf_bill"]), beta=with_se(t[6]["strategy"])[0])


# Puts the film's numbers in its data file, keeping the file's layout.
def write_film(numbers: dict[str, float]) -> None:
    text = FILM.read_text(encoding="utf-8")
    # Each number replaces the one value after its key, and only that.
    for key, value in numbers.items():
        text, hits = re.subn(rf'("{key}":\s*)[-0-9.eE+]+', rf"\g<1>{value}", text)
        if hits != 1:
            raise SystemExit(f"{FILM} has no single {key} to update.")
    FILM.write_text(text, encoding="utf-8")
    print(f"wrote {FILM.relative_to(ROOT)}: " + ", ".join(f"{k} {v}" for k, v in numbers.items()))


# A pack folder and a base site file, else the defaults.
def options(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Writes the site's data files from the pack.")
    parser.add_argument("--pack", type=Path, default=PACK, help="the numbers and charts pack")
    parser.add_argument("--base", type=Path, help="take the crowd and agents from this site file")
    return parser.parse_args(args)


# Writes the site's data, its crises and the film's numbers.
def main(args: list[str]) -> None:
    opts = options(args)
    base = opts.base or OUT
    if not base.exists():
        raise SystemExit(f"No {base}: pass --base with a site data file.")
    data = build(load(base), opts.pack)
    for out, made in ((OUT, data), (CRASHES, data["crises"])):
        out.write_text(json.dumps(made, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}: {out.stat().st_size / 1024:.0f} KB")
    write_film(film_numbers(opts.pack))


if __name__ == "__main__":
    main(sys.argv[1:])
