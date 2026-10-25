# Final v3's exhibits (docs/protocols/final_exhibits.md): edge and risk.

import json
import sys
import time

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from scipy.stats import norm

from fiam import book as P
from fiam import costs as C
from fiam import data, risk, stats, v2
from fiam.exhibits import september as S

OUT = v2.OUT / "final_exhibits"
NAIVE = ("naive_equal_model", "naive_equal_holdings", "favourites_held")
# Random books (section 1.1): draws, seed, top-N stocks, monthly swaps.
DRAWS, SEED, LARGEST, REPLACE = 1000, 42, 500, 0.1
# Published haircuts on a backtested information ratio (section 2).
HAIRCUTS = dict(mclean_pontiff_2016=0.26, harvey_liu_2015=0.50)


# Final v3's run name at a capital level.
def final_name(capital: float = 1e7) -> str:
    return v2.Settings(v2.final_three(), capital).name


# The record's cross-section with risk-model styles and specific risk.
def frame() -> pd.DataFrame:
    return v2.universe(v2.RECORD, v2.Settings(frozenset({"voltarget"})), v2.params())


# Each month's held names in risk-model order, weights and model terms.
def months(held: pd.DataFrame, df: pd.DataFrame):
    for eom, w in held.groupby("eom"):
        pool = df[(df["eom"] == eom) & df["permno"].isin(w["permno"])].reset_index(drop=True)
        weights = w.set_index("permno")["weight"].reindex(pool["permno"]).fillna(0.0).to_numpy()
        terms = v2.risk_terms(pool)
        if terms is not None:
            yield eom, pool, weights, terms


# 2026 panel months lack ticker and name, so each keeps its last known.
def labelled(table: pd.DataFrame) -> pd.DataFrame:
    known = data.features(["permno", "eom", "ticker", "company_name"]).dropna(subset=["ticker"])
    known = known.rename(columns={"ticker": "last_ticker", "company_name": "last_name"})
    out = pd.merge_asof(table.sort_values("eom"), known.sort_values("eom"), on="eom", by="permno")
    out["ticker"] = out["ticker"].fillna(out.pop("last_ticker"))
    out["company_name"] = out["company_name"].fillna(out.pop("last_name"))
    return out.sort_values(["eom", "permno"], ignore_index=True)


# Per-holding MCTR, CTR, PCTR and mismatch, plus monthly vol, VaR, CVaR.
def risk_table(name: str) -> dict:
    held = data.read(v2.OUT / name / "record" / "holdings.parquet")
    correction = v2.params().get("vol_bias", 1.0)
    rows, summary = [], []
    for eom, pool, w, (loadings, spec) in months(held, frame()):
        factor = loadings.T @ w
        covw = loadings @ factor + spec * w
        sigma = float(np.sqrt(w @ covw))
        mctr = covw / sigma
        pctr = w * mctr / sigma
        share = np.abs(w) / np.abs(w).sum()
        rows.append(
            pd.DataFrame(
                dict(
                    eom=eom,
                    permno=pool["permno"],
                    ticker=pool["ticker"],
                    company_name=pool["company_name"],
                    weight=w,
                    specific_vol=np.sqrt(spec),
                    mctr=mctr,
                    ctr=w * mctr,
                    pctr=pctr,
                    mismatch=pctr - share,
                )
            )
        )
        vol = sigma * correction
        summary.append(
            dict(
                eom=eom,
                names=int((w != 0).sum()),
                gross=float(np.abs(w).sum()),
                predicted_vol_month=sigma,
                corrected_vol_month=vol,
                corrected_vol_year=vol * np.sqrt(12),
                var_95=norm.ppf(0.95) * vol,
                cvar_95=norm.pdf(norm.ppf(0.95)) / 0.05 * vol,
                var_99=norm.ppf(0.99) * vol,
                cvar_99=norm.pdf(norm.ppf(0.99)) / 0.01 * vol,
                factor_share=float(factor @ factor) / sigma**2,
                top10_pctr=float(np.sort(pctr)[::-1][:10].sum()),
                largest_pctr=float(pctr.max()),
                mismatch_abs_mean=float(np.abs(pctr - share).mean()),
            )
        )
    table, months_ = labelled(pd.concat(rows, ignore_index=True)), pd.DataFrame(summary)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "risk_table.csv", index=False, lineterminator="\n")
    months_.to_csv(OUT / "risk_months.csv", index=False, lineterminator="\n")
    last = table[table["eom"] == table["eom"].max()].sort_values("pctr", ascending=False)
    keep = ["ticker", "company_name", "weight", "specific_vol", "mctr", "pctr", "mismatch"]
    return dict(
        run=name,
        months=len(months_),
        correction=correction,
        averages=months_.drop(columns="eom").mean().to_dict(),
        latest_month=str(months_["eom"].max().date()),
        latest_top=last.head(10)[keep].to_dict("records"),
    )


# Monthly style exposures per unit gross, and 24-month FF5 + UMD betas.
def exposures(name: str) -> dict:
    held = data.read(v2.OUT / name / "record" / "holdings.parquet")
    rows = []
    for eom, pool, w, _ in months(held, frame()):
        x = pool[list(risk.STYLES)].to_numpy()
        rows.append(dict(eom=eom, **dict(zip(risk.STYLES, x.T @ w / np.abs(w).sum()))))
    styles = pd.DataFrame(rows).set_index("eom")
    book = pd.read_csv(v2.OUT / name / "record" / "returns.csv", parse_dates=["holding_month"])
    net = book.set_index("holding_month")["net"]
    factors = stats.factors().reindex(net.index)
    loads = {}
    for end in range(24, len(net) + 1):
        y, x = net.iloc[end - 24 : end], factors.iloc[end - 24 : end]
        both = pd.concat([y.rename("r"), x], axis=1).dropna()
        if len(both) >= 18:
            fit = sm.OLS(both["r"], sm.add_constant(both[x.columns])).fit()
            loads[net.index[end - 1]] = fit.params[x.columns].to_dict()
    rolling = pd.DataFrame.from_dict(loads, orient="index")
    OUT.mkdir(parents=True, exist_ok=True)
    styles.to_csv(OUT / "style_exposures.csv", lineterminator="\n")
    rolling.to_csv(OUT / "rolling_loadings.csv", lineterminator="\n")
    by_year = styles.groupby(styles.index.year).mean()
    return dict(
        run=name,
        styles_by_year={str(y): r.round(2).to_dict() for y, r in by_year.iterrows()},
        styles_average=styles.mean().round(3).to_dict(),
        rolling_latest=rolling.iloc[-1].round(2).to_dict() if len(rolling) else {},
    )


# Equal-weight naive books like final v3, each a trial in the ledger.
def naive(kind: str, capital: float) -> dict:
    tag = f"{capital:.0e}".replace("+0", "")
    final = data.read(v2.OUT / final_name(capital) / "record" / "holdings.parquet")
    targets = {eom: w.set_index("permno")["weight"] for eom, w in final.groupby("eom")}
    favoured = favourites(final) if kind == "favourites_held" else None
    started = time.time()

    # The month's names by kind, equal within each side to final v3's gross.
    def optimize(month: pd.DataFrame, previous) -> pd.Series | None:
        target = targets.get(month["eom"].iloc[0])
        if target is None or not len(target):
            return None
        long, short = target[target > 0], target[target < 0]
        if kind == "naive_equal_model":
            ranked = month.sort_values("signal")["permno"]
            tops, bottoms = ranked.tail(len(long)).to_numpy(), ranked.head(len(short)).to_numpy()
        elif favoured is not None:
            here = set(month["permno"])
            tops = np.array(sorted(set(favoured[0]) & here))
            bottoms = np.array(sorted(set(favoured[1]) & here))
        else:
            tops, bottoms = long.index.to_numpy(), short.index.to_numpy()
        return pd.concat(
            [
                pd.Series(long.sum() / len(tops), index=tops),
                pd.Series(short.sum() / len(bottoms), index=bottoms),
            ]
        )

    df = v2.universe(v2.RECORD, v2.Settings(), v2.params())
    model = C.Model(nav=capital, impact_y=C.IMPACT_Y)
    rows, held = [], []
    for step in P.walk(df, optimize, True, model):
        month, weights, info = step[:3]
        record = P.month_record(*step)
        ret = info["ret_exc_lead1m"].reindex(weights.index).fillna(0.0)
        record["short_leg"] = float((weights[weights < 0] * ret[weights < 0]).sum())
        record["long_leg"] = float((weights[weights > 0] * ret[weights > 0]).sum())
        dolvol = info["dolvol_126d"].reindex(weights.index)
        days = weights.abs() * capital / (0.2 * dolvol)
        record["days_to_liquidate_max"] = float(days.max()) if len(weights) else 0.0
        rows.append(record)
        held.append(pd.DataFrame(dict(eom=month, permno=weights.index, weight=weights.to_numpy())))
    book = pd.DataFrame(rows).set_index("holding_month")
    folder = v2.OUT / f"{kind}@{tag}" / "record"
    folder.mkdir(parents=True, exist_ok=True)
    book.to_csv(folder / "returns.csv", lineterminator="\n")
    pd.concat(held, ignore_index=True).to_parquet(folder / "holdings.parquet", index=False)
    out = v2.summary(book, False)
    (folder / "stats.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    ledger = v2.OUT / "trials.csv"
    row = dict(
        when=pd.Timestamp.now().isoformat(timespec="seconds"),
        protocol="docs/protocols/final_exhibits.md",
        name=f"{kind}@{tag}",
        window="record",
        capital=capital,
        switches=kind,
        seconds=round(time.time() - started),
        information_ratio=out["information_ratio"],
    )
    pd.DataFrame([row]).to_csv(
        ledger, mode="a", header=not ledger.exists(), index=False, lineterminator="\n"
    )
    return out


# Final v3's most-held names (section 1.3): top net longs and shorts.
def favourites(held: pd.DataFrame) -> tuple[list, list]:
    months = held.groupby("eom")
    n_long = round(float(months["weight"].apply(lambda w: (w > 0).sum()).mean()))
    n_short = round(float(months["weight"].apply(lambda w: (w < 0).sum()).mean()))
    by_name = held.groupby("permno")["weight"].agg(size=lambda w: w.abs().sum(), side="sum")
    longs = by_name[by_name["side"] > 0].nlargest(n_long, "size").index.tolist()
    shorts = by_name[by_name["side"] < 0].nlargest(n_short, "size").index.tolist()
    return longs, shorts


# Section 1.1: random books of the 500 largest, paying final v3's costs.
def null(name: str) -> dict:
    held = data.read(v2.OUT / name / "record" / "holdings.parquet")
    book = pd.read_csv(v2.OUT / name / "record" / "returns.csv", parse_dates=["forecast_eom"])
    book = book.set_index("forecast_eom")
    rate = (book["cost"] / book["turnover"].where(book["turnover"] > 0)).fillna(0.0)
    df = v2.universe(v2.RECORD, v2.Settings(), v2.params())
    rng = np.random.default_rng(SEED)
    months = sorted(held["eom"].unique())
    largest, returns, legs = {}, {}, {}
    for eom in months:
        month = df[df["eom"] == eom]
        top = month.nlargest(LARGEST, "me")
        largest[eom] = top["permno"].to_numpy()
        returns[eom] = top.set_index("permno")["ret_exc_lead1m"].fillna(0.0)
        w = held[held["eom"] == eom]["weight"]
        legs[eom] = ((w > 0).sum(), (w < 0).sum(), w[w > 0].sum(), w[w < 0].sum())
    nets, grosses = np.zeros((DRAWS, len(months))), np.zeros((DRAWS, len(months)))
    for d in range(DRAWS):
        longs, shorts, before = [], [], pd.Series(dtype=float)
        for t, eom in enumerate(months):
            pool = largest[eom]
            n_long, n_short, g_long, g_short = legs[eom]
            keep = set(pool)
            longs = [p for p in longs if p in keep and rng.random() > REPLACE]
            shorts = [p for p in shorts if p in keep and rng.random() > REPLACE]
            free = np.setdiff1d(pool, longs + shorts)
            fresh = rng.permutation(free)
            need_long, need_short = max(n_long - len(longs), 0), max(n_short - len(shorts), 0)
            longs = (longs + fresh[:need_long].tolist())[:n_long]
            shorts = (shorts + fresh[need_long : need_long + need_short].tolist())[:n_short]
            w = pd.concat(
                [
                    pd.Series(g_long / max(len(longs), 1), index=longs),
                    pd.Series(g_short / max(len(shorts), 1), index=shorts),
                ]
            )
            idx = w.index.union(before.index)
            turnover = float(
                (w.reindex(idx, fill_value=0) - before.reindex(idx, fill_value=0)).abs().sum() / 2
            )
            gross = float((w * returns[eom].reindex(w.index).fillna(0.0)).sum())
            grosses[d, t] = gross
            nets[d, t] = gross - turnover * rate.get(eom, 0.0)
            before = w
    irs = np.array([P.information_ratio(pd.Series(n)) for n in nets])
    gross_irs = np.array([P.information_ratio(pd.Series(g)) for g in grosses])
    ours = P.information_ratio(book["net"])
    ours_gross = P.information_ratio(book["gross"])
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dict(ir=irs, gross_ir=gross_irs)).to_csv(OUT / "null_irs.csv", index=False)
    return dict(
        draws=DRAWS,
        seed=SEED,
        final_ir=ours,
        final_gross_ir=ours_gross,
        percentile=float((irs < ours).mean()),
        gross_percentile=float((gross_irs < ours_gross).mean()),
        mean=float(irs.mean()),
        p5=float(np.quantile(irs, 0.05)),
        p95=float(np.quantile(irs, 0.95)),
        best=float(irs.max()),
        gross_mean=float(gross_irs.mean()),
        gross_p95=float(np.quantile(gross_irs, 0.95)),
    )


# Section 1.2: final v3 run unchanged on the 500 largest stocks a month.
def large() -> dict:
    out = {}
    for cap in (1e7, 1e9):
        settings = v2.Settings(v2.final_three() | {"top500"}, cap)
        out[settings.name] = v2.run(settings, v2.RECORD)
    return out


# Section 2: final v3's live IR at each size after published haircuts.
def projection() -> dict:
    scored = json.loads((v2.OUT / "evidence.json").read_text(encoding="utf-8"))["v3"]
    out = {}
    for tag in ("1e7", "1e8", "5e8", "1e9", "5e9"):
        ir = scored.get(tag, {}).get("books", {}).get("final v3", {}).get("information_ratio")
        if ir is not None:
            out[tag] = dict(backtest=ir) | {k: ir * (1 - h) for k, h in HAIRCUTS.items()}
    return out


# The 30 largest September names, clustered by 1 - Spearman rank match.
def dendrogram() -> dict:
    book = pd.read_csv(S.FINAL)
    top = book.loc[book["weight"].abs().sort_values(ascending=False).index].head(30)
    chars = P.characteristics()
    panel = data.features(["permno", "eom", *chars])
    month = panel[panel["eom"] == S.DECISION].set_index("permno")
    ranks = month[chars].rank(pct=True).reindex(top["permno"])
    distance = (1 - ranks.T.corr(method="spearman")).clip(lower=0.0).fillna(1.0).to_numpy(copy=True)
    np.fill_diagonal(distance, 0.0)
    merges = linkage(squareform(distance, checks=False), "average")
    labels = data.features(["permno", "eom", "ticker"]).dropna(subset=["ticker"])
    labels = labels[labels["eom"] <= S.DECISION].sort_values("eom")
    ticker = labels.drop_duplicates("permno", keep="last").set_index("permno")["ticker"]
    names = [
        f"{ticker.get(p, str(p))} ({'L' if w > 0 else 'S'})"
        for p, w in zip(top["permno"], top["weight"])
    ]
    return dict(labels=names, weights=top["weight"].tolist(), linkage=merges.tolist())


# Runs the chosen exhibit parts, all by default, into report.json.
def main(parts: list[str]) -> None:
    path = OUT / "report.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    name = final_name()
    report["protocol"] = "docs/protocols/final_exhibits.md"
    if not parts or "null" in parts:
        report["null"] = null(name)
    if not parts or "large" in parts:
        report["large"] = large()
    if not parts or "projection" in parts:
        report["projection"] = projection()
    if not parts or "risk" in parts:
        report["risk_table"] = risk_table(name)
    if not parts or "exposures" in parts:
        report["exposures"] = exposures(name)
    if not parts or "naive" in parts:
        report["naive"] = {
            f"{kind}@{f'{cap:.0e}'.replace('+0', '')}": naive(kind, cap)
            for kind in NAIVE
            for cap in (1e7, 1e9)
        }
    if not parts or "dendrogram" in parts:
        report["dendrogram"] = dendrogram()
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "dendrogram"}, default=str)[:2500])


if __name__ == "__main__":
    main(sys.argv[1:])
