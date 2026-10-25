# AI Crowd Lab amendment 1, exploratory; nothing here enters v1 or v2.

import json
import sys

import numpy as np
import pandas as pd
from scipy import stats as st
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from fiam import book as P
from fiam import costs as C
from fiam import layers, v2
from fiam.agents import crowd_lab as L
from fiam.exhibits import crowd_lab as X
from fiam.exhibits import evidence as E
from fiam.freeze import FROZEN

OUT = v2.OUT / "crowd_insights.json"
TARIFFS = ("2025-03-31", "2025-04-30")
FLOWS = (1e9, 10e9, 50e9)
DRAWS, SEED = 10_000, 42


# v1's book in the crowds' months: weight and side by month and name.
def our_book(capital: str = "1e7") -> pd.DataFrame:
    held = E.load(f"v1@{capital}", "record")[1]
    return held.assign(side=np.sign(held["weight"]))


# Crowd months: v1's signal and the cost model's volatility and volume.
def market() -> pd.DataFrame:
    df = E.frame("record", frozenset())
    return df[df["eom"] >= L.FIRST][["eom", "permno", "signal", "rvol_21d", "dolvol_126d"]]


# 1. Copycats buying v1's longs and shorting its shorts, over base rate.
def copycat_test(picks: pd.DataFrame, book: pd.DataFrame, frame: pd.DataFrame) -> dict:
    df = picks.merge(book[["eom", "permno", "side"]], on=["eom", "permno"], how="left")
    df["side"] = df["side"].fillna(0.0)
    df = df.assign(
        long=df["side"] > 0,
        short=df["side"] < 0,
        buy_hit=df["picked"] & (df["side"] > 0),
        short_hit=df["shorted"] & (df["side"] < 0),
    )
    cols = ["picked", "shorted", "long", "short", "buy_hit", "short_hit"]
    rng, out = np.random.default_rng(SEED), {}
    for text, g in df.groupby("strategy"):
        months = g.groupby("eom")[cols].sum().assign(shown=g.groupby("eom").size())

        # Buy and short hit rates over base rates, pooled over the given months.
        def ratios(m: pd.DataFrame) -> tuple[float, float]:
            buy = (m["buy_hit"].sum() / m["picked"].sum()) / (m["long"].sum() / m["shown"].sum())
            sell = (m["short_hit"].sum() / m["shorted"].sum()) / (
                m["short"].sum() / m["shown"].sum()
            )
            return float(buy), float(sell)

        draws = np.array(
            [ratios(months.iloc[rng.integers(len(months), size=len(months))]) for _ in range(2000)]
        )
        votes = g.groupby(["eom", "permno"])[["picked", "shorted"]].mean()
        votes = (votes["picked"] - votes["shorted"]).rename("net").reset_index()
        votes = votes.merge(frame[["eom", "permno", "signal"]], on=["eom", "permno"])
        rho = votes.groupby("eom")[["net", "signal"]].apply(
            lambda v: v["net"].corr(v["signal"], "spearman")
        )
        buy, sell = ratios(months)
        out[text] = dict(
            buys_our_longs=buy,
            buys_ci95=np.quantile(draws[:, 0], [0.025, 0.975]).tolist(),
            shorts_our_shorts=sell,
            shorts_ci95=np.quantile(draws[:, 1], [0.025, 0.975]).tolist(),
            vote_signal_rho=float(rho.mean()),
        )
    return out


# 2. v1's cost if copycat money follows: square-root impact, bp a month.
def capacity_tax(picks: pd.DataFrame, frame: pd.DataFrame) -> dict:
    g = picks[picks["strategy"] == "v1"]
    votes = g.groupby(["eom", "permno"])[["picked", "shorted"]].mean()
    flow = (votes["picked"] - votes["shorted"]).rename("flow").reset_index()
    flow["flow"] /= flow.groupby("eom")["flow"].transform(lambda s: s.abs().sum())
    flow = flow.merge(frame, on=["eom", "permno"]).dropna(subset=["rvol_21d", "dolvol_126d"])
    out = {}
    for capital in ("1e7", "1e9"):
        held = our_book(capital).pivot_table(index="eom", columns="permno", values="weight")
        trades = held.fillna(0.0).diff().stack().rename("trade").reset_index()
        both = flow.merge(trades, on=["eom", "permno"])
        same = np.sign(both["trade"]) == np.sign(both["flow"])
        for money in FLOWS:
            impact = (
                C.IMPACT_Y
                * both["rvol_21d"]
                * np.sqrt(both["flow"].abs() * money / both["dolvol_126d"])
            )
            cost = (both["trade"].abs() * impact).where(same, 0.0).groupby(both["eom"]).sum()
            out[f"v1 at ${capital}, copycats ${money / 1e9:.0f}bn"] = float(cost.mean() * 1e4)
    return out


# 3. Crowd model's top ten likes and dislikes, and fit with our signal.
def what_it_buys(frame: pd.DataFrame) -> dict:
    model = json.loads((FROZEN / "crowd_emulator.json").read_text(encoding="utf-8"))
    names = json.loads((FROZEN / "characteristic_labels.json").read_text(encoding="utf-8"))
    coef = pd.Series(model["coef"], index=model["columns"]).sort_values()
    label = {c: names.get(c, c) for c in coef.index}
    scores = pd.read_parquet(v2.OUT / "crowd_scores.parquet")
    both = scores.merge(frame[["eom", "permno", "signal"]], on=["eom", "permno"])
    rho = both.groupby("eom")[["crowd_score", "signal"]].apply(
        lambda v: v["crowd_score"].corr(v["signal"], "spearman")
    )
    return dict(
        likes={label[c]: float(v) for c, v in coef.tail(10)[::-1].items()},
        dislikes={label[c]: float(v) for c, v in coef.head(10).items()},
        score_signal_rho=float(rho.mean()),
        ours=[label.get(c, c) for c in P.SIGNALS],
    )


# 4. Herding month by month against the VIX at the decision, per crowd.
def herding_and_fear(crowds: dict) -> dict:
    vix = layers.load("market/vix_daily")
    month_end = vix.set_index(pd.to_datetime(vix["date"]))["vix"].resample("ME").last()
    out = {}
    for name, picks in crowds.items():
        lsv = {m: X.lsv(g)["lsv"] for m, g in picks.groupby("eom")}
        series = pd.Series(lsv).sort_index()
        fear = month_end.reindex(series.index)
        # Only months with a VIX reading count; VIX can end before the votes do.
        seen = fear.notna()
        rho, p = st.spearmanr(series[seen], fear[seen])
        out[name] = dict(
            by_month={f"{m:%Y-%m}": dict(lsv=v, vix=float(fear[m])) for m, v in series.items()},
            spearman=float(rho),
            p=float(p),
            tariff_months={t: float(series.get(pd.Timestamp(t), np.nan)) for t in TARIFFS},
        )
    return out


# 5. Herding among the copycats given each strategy text.
def by_recipe(copycat: pd.DataFrame) -> dict:
    return {
        text: dict(lsv=X.lsv(g)["lsv"], **X.agreement(g)) for text, g in copycat.groupby("strategy")
    }


# 6. The crowd-alone what-if books before and after costs.
def before_costs() -> dict:
    out = {}
    for crowd, run in (
        ("retail", "crowd_alone+retail@1e7"),
        ("copycat", "copycat+crowd_alone@1e7"),
    ):
        loaded = E.load(run, "clean")
        if loaded:
            book = loaded[0]
            out[crowd] = dict(
                gross_ir=P.information_ratio(book["gross"]),
                net_ir=P.information_ratio(book["net"]),
                turnover=float(book["turnover"].mean()),
            )
    return out


# 7. Retail pick correlations grouped into the crowd's effective voters.
def network(retail: pd.DataFrame) -> dict:
    wide = retail.pivot_table(
        index=["eom", "permno"], columns="agent", values="picked", aggfunc="max"
    )
    corr = wide.astype(float).corr(min_periods=30).fillna(0.0)
    k = max(2, round(X.agreement(retail)["effective_voters"]))
    distance = squareform((1 - corr.to_numpy()).clip(min=0), checks=False)
    groups = fcluster(linkage(distance, "average"), k, criterion="maxclust")
    tags = retail.drop_duplicates("agent").set_index("agent")[["persona", "info_set"]]
    members = pd.DataFrame(dict(agent=corr.index, group=groups)).join(tags, on="agent")
    return dict(
        agents=[int(a) for a in corr.index],
        corr=corr.round(4).to_numpy().tolist(),
        groups=[int(g) for g in groups],
        mix={
            int(g): dict(
                personas=m["persona"].value_counts().to_dict(),
                info_sets={int(k): int(v) for k, v in m["info_set"].value_counts().items()},
            )
            for g, m in members.groupby("group")
        },
    )


# crowd.md item 6: our names in each crowd's top tenth; chance is 10%.
def overlap(crowds: dict, book: pd.DataFrame) -> dict:
    out = {}
    for name, picks in crowds.items():
        rows = []
        for month, g in picks.groupby("eom"):
            votes = g.groupby("permno")["picked"].agg(["mean", "size"])
            votes = votes[votes["size"] >= 3]
            fav = set(votes.index[votes["mean"].rank(pct=True) > 0.9])
            ours = book[book["eom"] == month].set_index("permno")["weight"]
            longs = [p for p in ours[ours > 0].index if p in votes.index]
            shorts = [p for p in ours[ours < 0].index if p in votes.index]
            rows.append((np.mean([p in fav for p in longs]), np.mean([p in fav for p in shorts])))
        longs, shorts = np.nanmean(rows, axis=0)
        out[name] = dict(longs_in_favourites=float(longs), shorts_in_favourites=float(shorts))
    return out


# A run's overlap and copycat test vs the crowds (final_exhibits.md).
def book(name: str) -> None:
    crowds, frame = X.crowds(), market()
    held = E.load(name, "record")[1]
    held = held.assign(side=np.sign(held["weight"]))
    report = json.loads(OUT.read_text(encoding="utf-8"))
    report[f"book {name}"] = dict(
        overlap=overlap(crowds, held), copycat_test=copycat_test(crowds["copycat"], held, frame)
    )
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps(report[f"book {name}"], default=float)[:1500])


# Every amendment 1 exhibit in one report, printed short for the log.
def main() -> None:
    crowds = X.crowds()
    frame, book = market(), our_book()
    report = dict(protocol="docs/protocols/crowd_amendment_1.md", exploratory=True)
    report["overlap"] = overlap(crowds, book)
    report["copycat_test"] = copycat_test(crowds["copycat"], book, frame)
    report["capacity_tax_bp_a_month"] = capacity_tax(crowds["copycat"], frame)
    report["what_it_buys"] = what_it_buys(frame)
    report["herding_and_fear"] = herding_and_fear(crowds)
    report["by_recipe"] = by_recipe(crowds["copycat"])
    report["before_costs"] = before_costs()
    report["network"] = network(crowds["retail"])
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(
        json.dumps({k: v for k, v in report.items() if k not in ("network",)}, default=float)[:3000]
    )


# uv run python -m fiam.exhibits.crowd_insights [book RUN]
if __name__ == "__main__":
    book(sys.argv[2]) if sys.argv[1:2] == ["book"] else main()
