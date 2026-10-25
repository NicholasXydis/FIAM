# Crash tests on the September books: 17 crises, scenarios, liquidity.

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam import book as P
from fiam import data, freeze
from fiam.exhibits import september as S

# CRSP daily from our extract, one parquet file per year.
DAILY = data.EXTRACTS / "crsp_daily"
CACHE = P.CACHE / "stress_daily.parquet"
OUT = Path("out") / "v2" / "stress.json"
FACTORS = ["mktrf", "smb", "hml", "rmw", "cma", "umd"]
CAPITALS = (1e7, 1e8, 1e9, 5e9)

# Seventeen crises from market events, and the scenarios (stress.md).
CRISES = {
    "Dot-com peak crash": ("2000-03-10", "2000-04-14"),
    "September 11": ("2001-09-10", "2001-09-21"),
    "Accounting scandals": ("2002-07-01", "2002-07-23"),
    "Quant unwind": ("2007-07-24", "2007-08-10"),
    "Bear Stearns": ("2008-03-03", "2008-03-17"),
    "Lehman and the crash": ("2008-09-12", "2008-10-27"),
    "Junk rally, momentum crash": ("2009-03-09", "2009-05-29"),
    "US downgrade": ("2011-07-22", "2011-08-19"),
    "Taper tantrum": ("2013-05-22", "2013-06-24"),
    "China devaluation": ("2015-08-18", "2015-08-25"),
    "Oil and high-yield sell-off": ("2016-01-04", "2016-02-11"),
    "Volatility spike": ("2018-01-26", "2018-02-08"),
    "Late-2018 sell-off": ("2018-10-03", "2018-12-24"),
    "Covid crash": ("2020-02-19", "2020-03-23"),
    "Vaccine rotation": ("2020-11-06", "2020-11-13"),
    "Rate shock": ("2022-01-03", "2022-06-16"),
    "Yen carry unwind": ("2024-07-31", "2024-08-05"),
}
SCENARIOS = {
    "Oil crash 2014-16": ("2014-06-20", "2016-02-11"),
    "Oil crash 2020": ("2020-03-06", "2020-04-21"),
    "Energy shock 2022": ("2022-02-24", "2022-06-08"),
    "Trade war, Mar 2018": ("2018-03-22", "2018-04-06"),
    "Trade war, Jun 2018": ("2018-06-15", "2018-07-06"),
    "Trade war, May 2019": ("2019-05-03", "2019-06-03"),
    "Trade war, Aug 2019": ("2019-08-01", "2019-08-23"),
}
SQUEEZE = ("2021-01-22", "2021-02-02")
SHORT_BAN = ("2008-09-19", "2008-10-08")


# Each episode's daily stock returns, read once from the extract.
def episode_returns() -> pd.DataFrame | None:
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    windows = [*CRISES.values(), *SCENARIOS.values(), SQUEEZE]
    years = {str(y) for first, last in windows for y in range(int(first[:4]), int(last[:4]) + 1)}
    files = sorted(p for p in DAILY.glob("*.parquet") if p.stem in years)
    if not files:
        print(f"warning: no CRSP daily extract in {DAILY}, replays are N/A", file=sys.stderr)
        return None
    cols = ["PERMNO", "SICCD", "DlyCalDt", "DlyRet", "DlyCap"]
    parts = []
    for path in files:
        chunk = pd.read_parquet(path, columns=cols)
        day = pd.to_datetime(chunk["DlyCalDt"])
        keep = np.zeros(len(chunk), dtype=bool)
        for first, last in windows:
            keep |= ((day >= first) & (day <= last)).to_numpy()
        part = chunk[keep].assign(date=day[keep])
        part["PERMNO"] = pd.to_numeric(part["PERMNO"]).astype("int64")
        part["ret"] = pd.to_numeric(part["DlyRet"], errors="coerce")
        parts.append(part[["PERMNO", "SICCD", "date", "ret", "DlyCap"]])
    out = pd.concat(parts, ignore_index=True).rename(
        columns={"PERMNO": "permno", "SICCD": "sic", "DlyCap": "cap"}
    )
    out["sic"] = pd.to_numeric(out["sic"], errors="coerce")
    CACHE.parent.mkdir(exist_ok=True)
    out.to_parquet(CACHE, index=False)
    return out


# The September books, v1, v2, v3 and final v3, as weights by permno.
def books() -> dict:
    out = {}
    for name, path in (("v1", S.V1), ("v2", S.V2), ("v3", S.V3), ("final v3", S.FINAL)):
        if path.exists():
            out[name] = pd.read_csv(path).set_index("permno")["weight"]
    return out


# One factor table from our WRDS extract; stops with the fix if absent.
def extract(name: str) -> pd.DataFrame:
    path = data.EXTRACTS / f"{name}.parquet"
    if not path.exists():
        raise SystemExit(f"No {path}: uv run run.py --data stock tables {name}")
    return pd.read_parquet(path)


# Daily FF5 + UMD factor returns from the extract.
def factor_daily() -> pd.DataFrame:
    table = extract("ff_daily")
    return table.assign(date=pd.to_datetime(table["date"])).set_index("date")[FACTORS]


# A book's factor loadings on its daily returns over the last 252 days.
def loadings(weights: pd.Series, factors: pd.DataFrame) -> pd.Series:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    wide = daily.pivot_table(index="date", columns="permno", values="total_return").tail(252)
    book = wide.reindex(columns=weights.index).fillna(0.0) @ weights
    both = pd.concat([book.rename("r"), factors], axis=1, join="inner").dropna()
    fit = sm.OLS(both["r"], sm.add_constant(both[FACTORS])).fit()
    return fit.params[FACTORS]


# Today's names through an episode, one not trading then uses its peers.
def replay(
    weights: pd.Series, panel: pd.DataFrame, first: str, last: str, info: pd.DataFrame
) -> dict:
    window = panel[(panel["date"] >= first) & (panel["date"] <= last)]
    if window.empty:
        return dict(loss=None, coverage=0.0)
    total = (1 + window.pivot_table(index="date", columns="permno", values="ret")).prod() - 1
    start = (
        window[window["date"] == window["date"].min()].drop_duplicates("permno").set_index("permno")
    )
    start["sic2"] = (start["sic"] // 100).astype("Int64")
    start["size"] = pd.qcut(start["cap"].rank(method="first"), 5, labels=False)
    peers = total.groupby(
        [start["sic2"].reindex(total.index), start["size"].reindex(total.index)]
    ).median()
    own = total.reindex(weights.index)
    covered = own.notna()
    sic2 = (info["sic"].reindex(weights.index) // 100).astype("Int64")
    # Our names are all above $300M, the fourth CRSP size quintile.
    size = pd.Series(3, index=weights.index)
    fill = [peers.get((s, z), np.nan) for s, z in zip(sic2, size)]
    filled = own.fillna(pd.Series(fill, index=weights.index)).fillna(0.0)
    return dict(
        loss=float((weights * filled).sum()),
        coverage=float(weights[covered].abs().sum() / weights.abs().sum()),
    )


# Two factors set to their episode moves, the rest to their expectation.
def conditional_shock(b: pd.Series, factors: pd.DataFrame, first: str, last: str) -> float:
    move = factors.loc[first:last].sum()
    base = factors.loc[:"2020-12-31"]
    sigma = base.cov()
    shocked = move.abs().nlargest(2).index
    rest = [f for f in FACTORS if f not in shocked]
    cond = sigma.loc[rest, shocked] @ np.linalg.solve(sigma.loc[shocked, shocked], move[shocked])
    full = pd.concat([move[shocked], pd.Series(cond, index=rest)])[FACTORS]
    return float(b @ full)


# The likeliest factor move costing 10% of NAV, and the closest month.
def reverse_stress(b: pd.Series) -> dict:
    monthly = extract("ff_monthly")
    monthly = monthly.assign(month=pd.to_datetime(monthly["dateff"])).set_index("month")[FACTORS]
    sigma = monthly.loc[:"2020-12-31"].cov().to_numpy()
    bv = b.to_numpy()
    f_star = -0.10 * sigma @ bv / (bv @ sigma @ bv)
    inv = np.linalg.inv(sigma)
    gaps = [(d, float((r - f_star) @ inv @ (r - f_star))) for d, r in monthly.iterrows()]
    closest = min(gaps, key=lambda x: x[1])[0]
    return dict(
        move={f: float(v) for f, v in zip(FACTORS, f_star)}, closest_month=f"{closest:%Y-%m}"
    )


# Days to sell each name at 10% of daily dollar volume, and forced path.
def liquidity(weights: pd.Series, info: pd.DataFrame, beta: pd.Series) -> dict:
    adv = info["dolvol_126d"].reindex(weights.index)
    adv = adv.fillna(adv.median())
    out = {}
    for nav in CAPITALS:
        days = weights.abs() * nav / (0.10 * adv)
        side = np.sign(weights)
        out[f"{nav:.0e}"] = {
            label: dict(
                weighted_mean=float((days[s] * weights[s].abs()).sum() / weights[s].abs().sum()),
                max=float(days[s].max()),
                over_one_day=int((days[s] > 1).sum()),
            )
            for label, s in (("long", side > 0), ("short", side < 0))
        }
    nav = 1e9
    left = weights.copy()
    path = []
    for day in range(1, 31):
        step = np.minimum(left.abs(), 0.10 * adv / nav) * np.sign(left)
        left = left - step
        path.append(dict(day=day, net=float(left.sum()), beta=float((left * beta).sum())))
        if left.abs().sum() < 1e-9:
            break
    out["unwind_at_1bn"] = dict(
        max_abs_net=max(abs(p["net"]) for p in path),
        max_abs_beta=max(abs(p["beta"]) for p in path),
        days=len(path),
    )
    return out


# Runs every test on each book and writes out/v2/stress.json.
def main() -> None:
    panel = episode_returns()
    factors = factor_daily()
    info = (
        P.load_panel(("sic",))
        .query("eom == @S.DECISION")
        .drop_duplicates("permno")
        .set_index("permno")
    )
    report = dict(
        protocol="docs/protocols/stress.md",
        source=DAILY.relative_to(data.ROOT).as_posix() if panel is not None else None,
    )
    for name, weights in books().items():
        b = loadings(weights, factors)
        entry = dict(loadings=b.to_dict(), crises={}, scenarios={})
        for label, (first, last) in CRISES.items():
            entry["crises"][label] = dict(factor_proxy=float(b @ factors.loc[first:last].sum()))
            if panel is not None:
                entry["crises"][label] |= replay(weights, panel, first, last, info)
        for label, (first, last) in SCENARIOS.items():
            entry["scenarios"][label] = dict(
                conditional_shock=conditional_shock(b, factors, first, last),
                factor_proxy=float(b @ factors.loc[first:last].sum()),
            )
            if panel is not None:
                entry["scenarios"][label] |= replay(weights, panel, first, last, info)
        if panel is not None:
            entry["squeeze_2021"] = replay(weights, panel, *SQUEEZE, info)
            ban = replay(
                weights[info["gics"].reindex(weights.index).astype(str).str[:2] == "40"],
                panel,
                *SHORT_BAN,
                info,
            )
            entry["financials_during_2008_short_ban"] = ban
        entry["reverse_stress"] = reverse_stress(b)
        # The September book's hedge beta: learned, then 60-month, then 1.
        rows = info.reindex(weights.index).reset_index()
        hedge = freeze.learned(rows).fillna(rows["beta_60m"]).fillna(1.0)
        beta = pd.Series(hedge.to_numpy(), index=weights.index)
        entry["liquidity"] = liquidity(weights, info, beta)
        report[name] = entry
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: v.get("reverse_stress", v) if isinstance(v, dict) else v
                for k, v in report.items()
            },
            indent=1,
            default=float,
        )
    )


if __name__ == "__main__":
    episode_returns() if sys.argv[1:] == ["extract"] else main()
