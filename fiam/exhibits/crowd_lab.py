# AI crowds: herding, the crowd model, crowding risk, vs short sellers.

import json
import sys

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as st

from fiam import book as P
from fiam import costs as C
from fiam import data, paths, stats
from fiam.agents import crowd_lab as L
from fiam.paths import FROZEN

EMULATOR = FROZEN / "agents" / "crowd_emulator.json"
OUT = paths.RESEARCH / "crowd_lab.json"
HISTORICAL = paths.EXHIBITS / "agents" / "crowd_picks.parquet"
CROWD_SIZES = (10e9, 50e9, 100e9)
# The plain book and its what-if runs, a crowd arm alone or copied.
PLAIN = paths.RESEARCH / "v1@1e7"
WHAT_IFS = ("crowd_*@1e7", "copycat+crowd_*@1e7")


# Each crowd's picks by agent and stock-month, with shorts for copycats.
def crowds() -> dict:
    out = {}
    for name in ("crowdlab_retail", "crowdlab_copycat"):
        if (L.H.RUNS / f"{name}.jsonl").exists():
            out[name.split("_")[1]] = L.picks(name)
    return out


# LSV herding (Lakonishok et al. 1992) on stock-months 3+ agents saw.
def lsv(picks: pd.DataFrame) -> dict:
    g = picks.groupby(["eom", "permno"])["picked"].agg(["sum", "count"])
    g = g[g["count"] >= 3]
    g["p"] = g["sum"] / g["count"]
    p_bar = g.groupby(level="eom")["p"].transform("mean")
    expected = [
        sum(st.binom.pmf(k, n, pb) * abs(k / n - pb) for k in range(n + 1))
        for n, pb in zip(g["count"], p_bar)
    ]
    h = (g["p"] - p_bar).abs() - np.array(expected)
    return dict(
        lsv=float(h.mean()), lsv_t=float(h.mean() / h.std() * np.sqrt(len(h))), cells=len(h)
    )


# Mean pairwise pick correlation on shared stocks, and effective voters.
def agreement(picks: pd.DataFrame, agents: list | None = None) -> dict:
    wide = picks.pivot_table(
        index=["eom", "permno"], columns="agent", values="picked", aggfunc="max"
    )
    if agents is not None:
        wide = wide[[a for a in agents if a in wide]]
    corr = wide.astype(float).corr(min_periods=30)
    n = corr.shape[0]
    rho = float(np.nanmean(corr.where(~np.eye(n, dtype=bool)).to_numpy()))
    eig = np.linalg.eigvalsh(np.nan_to_num(corr.to_numpy(), nan=0.0) + np.eye(n) * 0)
    return dict(
        agents=n,
        mean_correlation=rho,
        effective_voters=float(n / (1 + (n - 1) * rho)) if rho > -1 / max(n - 1, 1) else float(n),
        first_eigen_share=float(eig.max() / max(eig.sum(), 1e-12)),
    )


# Herding by shared information set versus by shared persona.
def diversity(picks: pd.DataFrame) -> dict:
    meta = picks.drop_duplicates("agent").set_index("agent")
    by_set = [
        agreement(picks, list(g.index))["mean_correlation"] for _, g in meta.groupby("info_set")
    ]
    by_persona = [
        agreement(picks, list(g.index))["mean_correlation"] for _, g in meta.groupby("persona")
    ]
    return dict(
        same_information_different_persona=float(np.nanmean(by_set)),
        same_persona_different_information=float(np.nanmean(by_persona)),
    )


# Buy share per stock-month: share of those who saw it that picked it.
def consensus(picks: pd.DataFrame) -> pd.DataFrame:
    vote = picks["picked"].astype(float) - picks.get("shorted", False)
    g = vote.groupby([picks["eom"], picks["permno"]]).mean().rename("consensus").reset_index()
    return g


# The 147 as 0-1 ranks for the crowd model, screened months 2015-2026.
def ranks(first: str = "2015-01-31", last: str = "2026-07-31") -> pd.DataFrame:
    chars = P.characteristics()
    frame = P.screen(P.load_panel(tuple(c for c in chars if c not in P.SIGNALS)), first, last)
    # Raw volatility and volume kept for the sell-off, as both get ranked.
    frame["vol_raw"], frame["dolvol_raw"] = frame["rvol_21d"], frame["dolvol_126d"]
    for col in chars:
        frame[col] = frame.groupby("eom")[col].rank(pct=True).fillna(0.5)
    return frame


# Ridge of consensus on the 147, year-block CV penalty, frozen as JSON.
def fit_emulator(frame: pd.DataFrame, targets: pd.DataFrame) -> dict:
    chars = P.characteristics()
    both = frame[[*data.KEYS, *chars]].merge(targets, on=data.KEYS)
    x, y = both[chars].to_numpy(), both["consensus"].to_numpy()
    years = both["eom"].dt.year.to_numpy()
    scores = {alpha: blocked_r2(x, y, years, alpha) for alpha in (1.0, 10.0, 100.0, 1000.0)}
    best = max(scores, key=lambda a: np.mean(scores[a]))
    model = ridge(x, y, best) | dict(alpha=best, columns=chars)
    model["r2_by_year_block"] = {str(y): float(r) for y, r in zip(np.unique(years), scores[best])}
    # Canaries: in-month shuffles and a firm-id column must explain nothing.
    rng = np.random.default_rng(42)
    shuffled = both.groupby("eom")["consensus"].transform(lambda s: rng.permutation(s.to_numpy()))
    identity = np.hstack([x, both[["permno"]].rank(pct=True).to_numpy()])
    model["canaries"] = dict(
        shuffled_r2=float(np.mean(blocked_r2(x, shuffled.to_numpy(), years, best))),
        identity_gain=float(np.mean(blocked_r2(identity, y, years, best)) - np.mean(scores[best])),
    )
    return model


# Out-of-sample R^2 with each year held out in turn.
def blocked_r2(x: np.ndarray, y: np.ndarray, years: np.ndarray, alpha: float) -> list[float]:
    out = []
    for test in np.unique(years):
        train = years != test
        pred = predict(ridge(x[train], y[train], alpha), x[~train])
        miss = ((y[~train] - pred) ** 2).sum()
        out.append(float(1 - miss / ((y[~train] - y[~train].mean()) ** 2).sum()))
    return out


# Closed-form ridge on centred inputs, as lists so it freezes to JSON.
def ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> dict:
    mu, ym = x.mean(axis=0), y.mean()
    xc = x - mu
    coef = np.linalg.solve(xc.T @ xc + alpha * np.eye(x.shape[1]), xc.T @ (y - ym))
    return dict(mean=mu.tolist(), intercept=float(ym), coef=coef.tolist())


# Scores rows with a frozen ridge, centred on its saved means.
def predict(model: dict, x: np.ndarray) -> np.ndarray:
    return model["intercept"] + (x - np.array(model["mean"])) @ np.array(model["coef"])


# Crowd score for any frame with the 147 as 0-1 ranks: level 0, no GPU.
def crowd_score(frame: pd.DataFrame) -> pd.Series:
    model = json.loads(EMULATOR.read_text(encoding="utf-8"))
    return pd.Series(predict(model, frame[model["columns"]].to_numpy()), index=frame.index)


# Crowding Index: long-short crowd score, percentile among random books.
def crowding_index(held: pd.DataFrame, scored: pd.DataFrame, draws: int = 1000) -> float:
    rng = np.random.default_rng(42)
    out = []
    for eom, w in held.groupby("eom"):
        month = scored[scored["eom"] == eom].set_index("permno")["crowd_score"]
        w = w.set_index("permno")["weight"]
        s = month.reindex(w.index).fillna(month.mean())
        ours = s[w > 0].mean() - s[w < 0].mean()
        n_long, n_short = int((w > 0).sum()), int((w < 0).sum())
        values = month.to_numpy()
        fake = [
            rng.choice(values, n_long).mean() - rng.choice(values, n_short).mean()
            for _ in range(draws // 10)
        ]
        out.append((np.array(fake) < ours).mean())
    return float(np.mean(out) * 100)


# Monthly return of the crowd's top minus bottom decile, equal weight.
def crowd_factor(scored: pd.DataFrame) -> pd.Series:
    rows = {}
    for eom, g in scored.dropna(subset=["ret_exc_lead1m"]).groupby("eom"):
        top = g["crowd_score"] >= g["crowd_score"].quantile(0.9)
        bottom = g["crowd_score"] <= g["crowd_score"].quantile(0.1)
        rows[(eom + pd.offsets.MonthBegin(1)).normalize()] = (
            g.loc[top, "ret_exc_lead1m"].mean() - g.loc[bottom, "ret_exc_lead1m"].mean()
        )
    return pd.Series(rows).sort_index()


# A book's beta to the crowd factor, with its Newey-West t.
def crowding_beta(net: pd.Series, factor: pd.Series) -> dict:
    both = pd.concat([net.rename("r"), factor.rename("f")], axis=1).dropna()
    fit = sm.OLS(both["r"], sm.add_constant(both["f"])).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return dict(beta=float(fit.params["f"]), t=float(fit.tvalues["f"]), months=len(both))


# A book's loss if the crowd sells favourites over 5 days, sqrt impact.
def sell_off(held_month: pd.Series, month: pd.DataFrame, crowd_size: float) -> float:
    top = month[month["crowd_score"] >= month["crowd_score"].quantile(0.9)].set_index("permno")
    sold = crowd_size / len(top) / 5
    sigma = top["vol_raw"].fillna(top["vol_raw"].median())
    dollars = top["dolvol_raw"].fillna(top["dolvol_raw"].median())
    drop = np.minimum(sigma * np.sqrt(sold / dollars) * np.sqrt(5), 1.0)
    return float(-(held_month.reindex(drop.index).fillna(0.0) * drop).sum())


# Monthly share of our long and short weight in the crowd's top decile.
def signature(held: pd.DataFrame, scored: pd.DataFrame) -> dict:
    out = {}
    for eom, w in held.groupby("eom"):
        month = scored[scored["eom"] == eom]
        top = set(month.loc[month["crowd_score"] >= month["crowd_score"].quantile(0.9), "permno"])
        w = w.set_index("permno")["weight"]
        in_top = w.index.isin(top)
        long, short = w[w > 0], -w[w < 0]
        out[f"{eom:%Y-%m}"] = dict(
            long=float(long[in_top[w.values > 0]].sum() / long.sum()) if len(long) else 0.0,
            short=float(short[in_top[w.values < 0]].sum() / short.sum()) if len(short) else 0.0,
        )
    return out


# Monthly crowd consensus vs short interest, published a month late.
def versus_short_sellers(cons: pd.DataFrame) -> dict:
    ratio = C.short_ratio()
    if ratio is None:
        return dict(skipped="no short-interest layer")
    both = cons.join(ratio.rename("short"), on=data.KEYS).dropna()
    rho = (
        both.groupby("eom")[["consensus", "short"]].corr(method="spearman").xs("consensus", level=1)
    )
    monthly = rho["short"]
    top = both[both["consensus"] >= both.groupby("eom")["consensus"].transform("quantile", 0.9)]
    crowded = both.groupby("eom")["short"].transform("quantile", 0.9)
    share = (top["short"] >= crowded.loc[top.index]).mean()
    return dict(
        spearman_mean=float(monthly.mean()),
        t=float(monthly.mean() / monthly.std() * np.sqrt(len(monthly)))
        if len(monthly) > 1
        else None,
        months=len(monthly),
        crowd_top_in_short_top_share=float(share),
        chance=0.10,
    )


# Replays: reruns should match, perturbed cards drift as the move grows.
def replay_checks(log: str) -> dict:
    out = {}
    for kind, col in (("rerun", "cached"), ("perturbed", "original")):
        path = L.H.RUNS / f"{log}_{kind}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
        both = [(set(r["picked"]), set(r[col]), r.get("move", 0)) for r in rows]
        agree = pd.Series([len(a & b) / len(a | b) if a | b else 1.0 for a, b, _ in both])
        out[kind] = dict(cards=len(rows), agreement=float(agree.mean()))
        if kind == "perturbed":
            moves = pd.Series([m for *_, m in both])
            out[kind]["by_move"] = agree.groupby(pd.cut(moves, [0, 3, 6, 10])).mean().to_dict()
            out[kind]["by_move"] = {str(k): float(v) for k, v in out[kind]["by_move"].items()}
    return out


# Same-side overlap of two books, Jaccard on month, name and side.
def overlap(a: pd.DataFrame, b: pd.DataFrame) -> float:
    sa = set(zip(a["eom"], a["permno"], np.sign(a["weight"])))
    sb = set(zip(b["eom"], b["permno"], np.sign(b["weight"])))
    return len(sa & sb) / len(sa | sb) if sa | sb else float("nan")


# What-if books against the plain one, reported with no pass or fail.
def what_if() -> dict:
    out = {}
    found = (f for pattern in WHAT_IFS for f in paths.RESEARCH.glob(f"{pattern}/*"))
    for folder in sorted(found):
        if not (folder / "stats.json").exists():
            continue
        for book in (folder, PLAIN / folder.name):
            net = pd.read_csv(book / "returns.csv")["net"]
            s = json.loads((book / "stats.json").read_text())
            out[f"{book.parent.name} {book.name}"] = dict(
                information_ratio=s["information_ratio"],
                max_drawdown=stats.drawdown(net),
                turnover=s["turnover"],
                overlap_with_plain=overlap(
                    data.read(book / "holdings.parquet"),
                    data.read(PLAIN / folder.name / "holdings.parquet"),
                ),
            )
    return out


# Each run's crowd exposure: beta, index, signature and sell-off cost.
def exposures(names: tuple, scored: pd.DataFrame, factor: pd.Series) -> dict:
    out = {}
    for name in names:
        for window in ("check", "record"):
            folder = paths.RESEARCH / name / window
            if not (folder / "returns.csv").exists():
                continue
            book = pd.read_csv(folder / "returns.csv", parse_dates=["holding_month"])
            held = data.read(folder / "holdings.parquet")
            entry = dict(
                crowding_beta=crowding_beta(book.set_index("holding_month")["net"], factor),
                crowding_index=crowding_index(held, scored),
                signature=signature(held, scored),
            )
            last = held["eom"].max()
            month = scored[scored["eom"] == last]
            weights = held[held["eom"] == last].set_index("permno")["weight"]
            entry["sell_off_cost"] = {
                f"{size / 1e9:.0f}bn": sell_off(weights, month, size) for size in CROWD_SIZES
            }
            out[f"{name} {window}"] = entry
    return out


# A run's exposure added from the frozen crowd model, nothing refitted.
def book(name: str) -> None:
    frame = ranks()
    scored = frame[[*data.KEYS, "ret_exc_lead1m", "vol_raw", "dolvol_raw"]].copy()
    scored["crowd_score"] = crowd_score(frame)
    report = json.loads(OUT.read_text(encoding="utf-8"))
    report |= exposures((name,), scored, crowd_factor(scored))
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k.startswith(name)}, default=float))


# Every crowd measure on answers so far, and the crowd model frozen.
def main() -> None:
    report = dict(protocol="frozen/v1/protocols/crowd.md")
    live = crowds()
    for name, picks in live.items():
        report[name] = dict(
            answers=int(picks.groupby(["agent", "eom"]).ngroups),
            herding=lsv(picks),
            agreement=agreement(picks),
        )
        report[name]["replay_checks"] = replay_checks(f"crowdlab_{name}")
        if name == "retail":
            report[name]["diversity"] = diversity(picks)
            report[name]["vs_short_sellers"] = versus_short_sellers(consensus(picks))
    frame = ranks()
    hist = data.read(HISTORICAL)
    votes = {name: consensus(p) for name, p in live.items()}
    votes["historical"] = consensus(hist)
    saved = pd.concat([v.assign(crowd=k) for k, v in votes.items()], ignore_index=True)
    saved.to_parquet(paths.RESEARCH / "crowd_consensus.parquet", index=False)
    targets = [v for k, v in votes.items() if k in ("retail", "historical")]
    model = fit_emulator(frame, pd.concat(targets, ignore_index=True))
    EMULATOR.parent.mkdir(parents=True, exist_ok=True)
    EMULATOR.write_text(json.dumps(model) + "\n", encoding="utf-8")
    report["emulator"] = {k: model[k] for k in ("alpha", "r2_by_year_block", "canaries")}
    scored = frame[[*data.KEYS, "ret_exc_lead1m", "vol_raw", "dolvol_raw"]].copy()
    scored["crowd_score"] = crowd_score(frame)
    factor = crowd_factor(scored)
    scored[[*data.KEYS, "crowd_score"]].to_parquet(
        paths.RESEARCH / "crowd_scores.parquet", index=False
    )
    report |= exposures((PLAIN.name,), scored, factor)
    report["what_if"] = what_if()
    OUT.write_text(json.dumps(report, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "emulator"}, indent=1, default=float))


# uv run python -m fiam.exhibits.crowd_lab [book RUN]
if __name__ == "__main__":
    book(sys.argv[2]) if sys.argv[1:2] == ["book"] else main()
