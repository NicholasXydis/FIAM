# Teachers: models that learn what 2025-only data would say, from inputs that reach 2026.


import lightgbm as lgb
import numpy as np
import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import data, paths
from fiam.ml import dataset as D
from fiam.ml import text as T

OUT = paths.EXHIBITS / "teachers.json"
CACHE = P.CACHE / "teachers.parquet"

# The 8-K counts every model may read, all known by the month's end.
EVENTS = ["filing_count", "amendment_count", "word_count", "text_negative", "text_uncertainty"]
EVENTS += ["text_positive", "item_101_contract", "item_102_contract_termination"]
EVENTS += ["item_201_acquisition", "item_202_earnings", "item_205_impairment", "item_206_distress"]
EVENTS += ["item_401_auditor_change", "item_402_nonreliance", "item_502_management_change"]
EVENTS += ["item_701_regfd", "item_801_other_event"]

# Fixed settings, never tuned on a test year. Four threads on every machine, so runs repeat.
PARAMS = dict(
    objective="regression",
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=1000,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=10.0,
    num_threads=4,
    seed=42,
    deterministic=True,
    force_row_wise=True,
    verbosity=-1,
)
ROUNDS = 20 if paths.SMOKE else 300
YEARS = range(2024 if paths.SMOKE else 2017, 2027)


# The 147 characteristics ranked within each month, plus that month's 8-K counts.
def inputs() -> tuple[pd.DataFrame, list[str]]:
    frame = D.load_folds()
    events = data.features(EVENTS)
    frame = frame.merge(events, on=data.KEYS, how="left")
    return frame, [*P.characteristics(), *EVENTS]


# Each stock's beta to the S&P 500 inside each calendar month, from its daily returns.
def monthly_beta() -> pd.Series | None:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    if daily is None:
        return None
    close = pd.read_csv(B.pinned("SP500.csv"), parse_dates=["observation_date"]).dropna()
    market = close.set_index("observation_date")["SP500"].pct_change().rename("m")
    frame = daily.join(market, on="date").dropna(subset=["total_return", "m"])
    frame["month"] = frame["date"].dt.to_period("M").dt.to_timestamp()
    frame["rm"], frame["mm"] = frame["total_return"] * frame["m"], frame["m"] ** 2
    g = frame.groupby(["permno", "month"])
    s = g[["total_return", "m", "rm", "mm"]].sum()
    n = g.size()
    cov = s["rm"] - s["total_return"] * s["m"] / n
    var = s["mm"] - s["m"] ** 2 / n
    beta = (cov / var.where(var > 0)).where(n >= 15)
    return beta.clip(-1.0, 4.0).rename("target")


# Shares sold short as a share of shares outstanding, at each month's end.
def monthly_crowding() -> pd.Series | None:
    short = data.research(
        "short_interest_monthly_research_only", [*data.KEYS, "short_interest_adjusted"]
    )
    if short is None:
        return None
    shares = data.features(["shares"])
    both = short.merge(shares, on=data.KEYS)
    ratio = both["short_interest_adjusted"] / (both["shares"] * 1e6)
    month = (both["eom"] + pd.offsets.MonthBegin(-1)).dt.normalize()
    return pd.Series(ratio.to_numpy(), index=pd.MultiIndex.from_arrays([both["permno"], month]))


# Net analyst price-target revisions in each month, up minus down over the number of analysts.
def monthly_revisions() -> pd.Series | None:
    cols = ["ibes_pt_numup1m", "ibes_pt_numdown1m", "ibes_pt_numest"]
    ibes = data.research("ibes_monthly_research_only", [*data.KEYS, *cols])
    if ibes is None:
        return None
    net = (ibes["ibes_pt_numup1m"] - ibes["ibes_pt_numdown1m"]) / ibes["ibes_pt_numest"].clip(1)
    month = (ibes["eom"] + pd.offsets.MonthBegin(-1)).dt.normalize()
    return pd.Series(net.to_numpy(), index=pd.MultiIndex.from_arrays([ibes["permno"], month]))


# Next quarter's surprise: niq_su a month after the next report (rdq), if due within four months.
def monthly_surprise() -> pd.Series | None:
    quarters = data.wrds("compustat_quarterly", ["gvkey", "rdq"])
    if quarters is None:
        return None
    reports = quarters.dropna().assign(
        rdq=lambda d: pd.to_datetime(d["rdq"]).astype("datetime64[s]")
    )
    reports = reports.drop_duplicates().sort_values("rdq").rename(columns={"rdq": "report"})
    panel = data.features(["gvkey", "niq_su"]).dropna(subset=["gvkey"])
    decided = pd.merge_asof(
        panel[["permno", "eom", "gvkey"]].sort_values("eom"),
        reports,
        left_on="eom",
        right_on="report",
        by="gvkey",
        direction="forward",
        allow_exact_matches=False,
    )
    decided = decided[(decided["report"] - decided["eom"]).dt.days <= 122]
    decided["when"] = (decided["report"] + pd.DateOffset(months=1)) + pd.offsets.MonthEnd(0)
    known = panel.set_index(["permno", "eom"])["niq_su"]
    value = known.reindex(pd.MultiIndex.from_arrays([decided["permno"], decided["when"]]))
    month = (decided["eom"] + pd.offsets.MonthBegin(1)).dt.normalize()
    return pd.Series(value.to_numpy(), index=pd.MultiIndex.from_arrays([decided["permno"], month]))


# Each row's target: what the layer shows in the holding month, the month after the decision.
def attach(frame: pd.DataFrame, target: pd.Series, rank: bool) -> pd.Series:
    key = pd.MultiIndex.from_arrays([frame["permno"], frame["holding_month"]])
    values = pd.Series(target.reindex(key).to_numpy(), index=frame.index)
    return values.groupby(frame["holding_month"]).rank(pct=True) - 0.5 if rank else values


# Year by year, trained only on holding months before that year. Never sees its own year.
def walk_forward(frame: pd.DataFrame, cols: list[str], target: pd.Series, text=None) -> pd.Series:
    out = pd.Series(np.nan, index=frame.index)
    year = frame["holding_month"].dt.year
    for test_year in YEARS:
        train = (year < test_year) & target.notna()
        test = year == test_year
        if train.sum() < 10_000 or not test.any():
            continue
        x = frame[cols]
        # Text components fitted on the training years alone, so the test year never shapes them.
        if text is not None:
            parts = T.components(text, (year < test_year).to_numpy())
            x = pd.concat([x, pd.DataFrame(parts, index=frame.index, columns=T.NAMES)], axis=1)
        model = lgb.train(PARAMS, lgb.Dataset(x.loc[train], label=target[train]), ROUNDS)
        out[test] = model.predict(x.loc[test], num_threads=PARAMS["num_threads"])
    return out


# How well each teacher's year-ahead prediction matched what happened, year by year.
def accuracy(frame: pd.DataFrame, pred: pd.Series, target: pd.Series, name: str) -> dict:
    both = pd.DataFrame(dict(p=pred, t=target, y=frame["holding_month"].dt.year)).dropna()
    by_year = {str(y): float(g["p"].corr(g["t"], method="spearman")) for y, g in both.groupby("y")}
    out = dict(rank_correlation_by_year=by_year, rows=int(len(both)))
    if name == "beta":
        raw = data.features(["beta_60m"]).set_index(data.KEYS)["beta_60m"]
        old = pd.Series(raw.reindex(pd.MultiIndex.from_frame(frame[data.KEYS])).to_numpy())
        old.index = frame.index
        both = both.join(old.rename("old")).dropna()
        out["mean_abs_error"] = float((both["p"] - both["t"]).abs().mean())
        out["beta_60m_mean_abs_error"] = float((both["old"] - both["t"]).abs().mean())
    return out


# Each teacher learned year by year, its predictions cached and scored.
def main() -> None:
    frame, cols = inputs()
    layers = dict(beta=(monthly_beta, False), crowding=(monthly_crowding, True))
    layers["revisions"] = (monthly_revisions, True)
    layers["surprise"] = (monthly_surprise, True)
    out = frame[[*data.KEYS]].copy()
    report = {}
    for name, (build, rank) in layers.items():
        raw = build()
        if raw is None:
            print(f"  {name}: its layer is not in the bundle, skipped")
            continue
        target = attach(frame, raw, rank)
        # Only the earnings-surprise teacher reads the text, as PREREGISTRATION.md fixes.
        text = T.aligned(frame) if name == "surprise" else None
        pred = walk_forward(frame, cols, target, text)
        out[f"{name}_hat"] = pred
        report[name] = accuracy(frame, pred, target, name)
        print(f"  {name}: {report[name]['rank_correlation_by_year']}")
    CACHE.parent.mkdir(exist_ok=True)
    out.to_parquet(CACHE, index=False)
    summary = dict(
        what="Year-ahead predictions of daily beta, short-interest crowding, analyst revisions and "
        "next quarter's earnings surprise, each trained only on earlier years from the "
        "characteristics and 8-K counts; the surprise teacher also reads the text components.",
        teachers=report,
    )
    paths.write_json(OUT, summary)


if __name__ == "__main__":
    main()
