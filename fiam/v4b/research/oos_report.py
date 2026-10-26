"""Comprehensive post-run diagnostics for the corrected 2021-2026 E3 run."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "fiam/v4b/out/nautilus_oos"
E3 = OUT / "E3"
PREMIUM = 0.04


def cash_rate(index):
    t = pd.read_csv(ROOT / "data/benchmarks/TB3MS.csv", parse_dates=["observation_date"])
    m = t.set_index(t["observation_date"].dt.to_period("M"))["TB3MS"]
    return pd.Series(index.to_period("M").map(m).to_numpy() / 25200.0, index=index)


def load_ff():
    z = zipfile.ZipFile(ROOT / "data/benchmarks/ff5_daily.zip")
    raw = z.read(z.namelist()[0]).decode("utf8", "ignore").splitlines()
    head = next(i for i, x in enumerate(raw) if x.startswith(",Mkt-RF"))
    d = pd.read_csv(io.StringIO("\n".join(raw[head:])))
    d = d.rename(columns={d.columns[0]: "date"})
    d = d[d.date.astype(str).str.fullmatch(r"\d{8}")]
    d["date"] = pd.to_datetime(d.date.astype(str), format="%Y%m%d")
    return d.set_index("date").apply(pd.to_numeric, errors="coerce") / 100


def hac(y, x):
    both = pd.concat([y.rename("y"), x.rename("x")], axis=1, join="inner").dropna()
    X = np.column_stack([np.ones(len(both)), both["x"].to_numpy()])
    coef, *_ = np.linalg.lstsq(X, both["y"].to_numpy(), rcond=None)
    e = both["y"].to_numpy() - X @ coef
    xe = X * e[:, None]
    s = xe.T @ xe
    for k in range(1, 4):
        g = xe[k:].T @ xe[:-k]
        s += (1 - k / 4) * (g + g.T)
    cov = np.linalg.inv(X.T @ X) @ s @ np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return {"alpha": float(coef[0]), "beta": float(coef[1]),
            "beta_se": float(se[1]), "beta_t": float(coef[1] / se[1]), "n": int(len(both))}


def parse_nav(path):
    text = Path(path).read_text()
    rows = [(pd.Timestamp(d), float(n.replace(",", "")))
            for d, n in re.findall(r"E3 (\d{4}-\d{2}-\d{2}) native NAV ([\d,]+)", text)]
    return pd.Series(dict(rows)).sort_index()


def main():
    summary = json.loads((E3 / "summary.json").read_text())
    led_full = pd.read_parquet(E3 / "daily_nav.parquet").sort_index()
    led_full.index = pd.to_datetime(led_full.index)
    nav_prev_full = led_full["nav"].shift(1)
    led = led_full
    if led.index[0] == pd.Timestamp("2020-12-31"):
        led = led.iloc[1:]
    nav_prev = nav_prev_full.reindex(led.index)
    rf = cash_rate(led.index)
    bench = rf + PREMIUM / 252
    active = led["ret"] - bench
    costs = led[["spread", "impact", "fees", "borrow"]].sum(axis=1)
    gross = led["ret"] + (costs / nav_prev).fillna(0.0)

    def mret(s):
        return (1 + s).resample("ME").prod() - 1

    monthly = mret(led["ret"])
    monthly_bench = mret(bench)
    monthly_active = monthly - monthly_bench
    monthly_gross = mret(gross)
    drawdown = led["nav"] / led["nav"].cummax() - 1
    rolling = monthly_active.rolling(12).mean() / monthly_active.rolling(12).std(ddof=1) * np.sqrt(12)

    ff = load_ff()
    fmonth = (1 + ff).resample("ME").prod() - 1
    x = pd.concat([monthly_active.rename("active"), fmonth], axis=1).dropna()
    cols = [c for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"] if c in x]
    X = np.column_stack([np.ones(len(x)), x[cols].to_numpy()])
    y = x["active"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ coef
    r2 = 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    sp = pd.read_csv(ROOT / "data/benchmarks/SP500.csv", parse_dates=["observation_date"],
                     na_values=["."]).set_index("observation_date")["SP500"]
    sp = sp.reindex(led.index).pct_change(fill_method=None)
    beta = hac(led["ret"] - rf, sp - rf)

    years = {}
    for yy, g in led.groupby(led.index.year):
        gp = gross.reindex(g.index)
        years[str(int(yy))] = {
            "sessions": int(len(g)),
            "net_return": float((1 + g["ret"]).prod() - 1),
            "gross_return": float((1 + gp).prod() - 1),
            "benchmark_return": float((1 + bench.reindex(g.index)).prod() - 1),
            "active_pp": float(((1 + g["ret"]).prod() - 1) - ((1 + bench.reindex(g.index)).prod() - 1)),
            "net_ir": float((g["ret"] - bench.reindex(g.index)).mean() / (g["ret"] - bench.reindex(g.index)).std(ddof=1) * np.sqrt(252)),
            "vol_ann": float(g["ret"].std(ddof=1) * np.sqrt(252)),
            "max_drawdown": float(((1 + g["ret"]).cumprod() / (1 + g["ret"]).cumprod().cummax() - 1).min()),
            "cost_pct_nav": float((costs.reindex(g.index) / nav_prev.reindex(g.index)).sum()),
            "spread_pct_nav": float((g["spread"] / nav_prev.reindex(g.index)).sum()),
            "impact_pct_nav": float((g["impact"] / nav_prev.reindex(g.index)).sum()),
            "fees_pct_nav": float((g["fees"] / nav_prev.reindex(g.index)).sum()),
            "borrow_pct_nav": float((g["borrow"] / nav_prev.reindex(g.index)).sum()),
        }
    full_years = len(led) / 252
    nav0 = 1_000_000_000.0
    full = {
        "net_return": float(led["nav"].iloc[-1] / nav0 - 1),
        "gross_return": float((1 + gross).prod() - 1),
        "benchmark_return": float((1 + bench).prod() - 1),
        "cagr": float((led["nav"].iloc[-1] / nav0) ** (1 / full_years) - 1),
        "ann_vol": float(led["ret"].std(ddof=1) * np.sqrt(252)),
        "net_ir": float(active.mean() / active.std(ddof=1) * np.sqrt(252)),
        "max_drawdown": float(drawdown.min()),
        "end_drawdown": float(drawdown.iloc[-1]),
        "cost_pct_nav_yr": float((costs / nav_prev).sum() / full_years),
        "turnover_annualised": float(led["turnover"].sum() / full_years),
        "start": str(led.index[0].date()), "end": str(led.index[-1].date()),
    }

    # 2021-2025 vs 2026.
    part = {}
    for label, mask in [
        ("2021_2025", led.index.year <= 2025),
        ("2026_jan_jul", (led.index.year == 2026) & (led.index <= "2026-07-31")),
        ("2026_jan_aug", led.index.year == 2026),
    ]:
        g = led[mask]
        part[label] = {"net_return": float((1 + g["ret"]).prod() - 1),
                       "sessions": int(len(g))}

    # March 2021 long/short decomposition using actual prior-close weights.
    pos = pd.read_parquet(E3 / "daily_holdings.parquet", columns=["date", "permno", "w"])
    pos["date"] = pd.to_datetime(pos["date"])
    mar_pos = pos[(pos["date"] >= "2021-02-25") & (pos["date"] <= "2021-03-31")].sort_values(["permno", "date"])
    mar_pos["date_next"] = mar_pos.groupby("permno")["date"].shift(-1)
    mar_ret = pd.read_parquet(
        ROOT / "data/fiam_v1/daily_market_2026.parquet",
        columns=["permno", "date", "total_return"],
        filters=[("date", ">=", pd.Timestamp("2021-03-01")),
                 ("date", "<=", pd.Timestamp("2021-03-31"))],
    ).drop_duplicates(["permno", "date"])
    mar_ret["date"] = pd.to_datetime(mar_ret["date"])
    mar = mar_pos.merge(mar_ret, left_on=["permno", "date_next"],
                        right_on=["permno", "date"], suffixes=("", "_r"))
    mar["contrib"] = mar["w"] * mar["total_return"]
    march_cost = float((led.loc["2021-03-01":"2021-03-31", ["spread", "impact", "fees", "borrow"]].sum(axis=1)
                        / led["nav"].shift(1).reindex(led.loc["2021-03-01":"2021-03-31"].index)).sum())
    march = {
        "long_sum": float(mar.loc[mar["w"] > 0, "contrib"].sum()),
        "short_sum": float(mar.loc[mar["w"] < 0, "contrib"].sum()),
        "total_sum": float(mar["contrib"].sum()),
        "cost_from_ledger": march_cost,
        "net_from_ledger": float((1 + led.loc["2021-03-01":"2021-03-31", "ret"]).prod() - 1),
        "top_long": {str(k): float(v) for k, v in mar[mar.w > 0].groupby("permno")["contrib"].sum().nlargest(5).items()},
        "top_short": {str(k): float(v) for k, v in mar[mar.w < 0].groupby("permno")["contrib"].sum().nsmallest(5).items()},
    }

    # Regime overlay: scale the month's net return when the prior month-end gate is on.
    gate = pd.read_csv(OUT / "regime_monthly.csv", index_col=0, parse_dates=True)
    gs = gate["gate_short"].reindex(monthly.index - pd.offsets.MonthEnd(1)).fillna(False).to_numpy()
    ge = (gate["gate_short"] | gate["gate_risk"]).reindex(monthly.index - pd.offsets.MonthEnd(1)).fillna(False).to_numpy()
    overlay = {}
    for name, mask, mult in [("month_end_short_half", gs, 0.5),
                             ("month_end_short_zero", gs, 0.0),
                             ("month_end_either_half", ge, 0.5)]:
        rr = np.where(mask, monthly.to_numpy() * mult, monthly.to_numpy())
        overlay[name] = {
            "gated_months": int(mask.sum()),
            "2021": float(np.prod(1 + rr[monthly.index.year == 2021]) - 1),
            "2022": float(np.prod(1 + rr[monthly.index.year == 2022]) - 1),
            "2021_2026": float(np.prod(1 + rr) - 1),
        }
    # Daily Vireo-style gate applied to the strategy's daily net return.  This
    # is a post-hoc exposure overlay, not a rerun; it ignores the extra turnover
    # from switching in and out of the gate.
    reg = pd.read_parquet(OUT / "regime_daily.parquet")
    daily_gate = reg["gate_short"].reindex(led.index).fillna(False).to_numpy()
    daily_either = (reg["gate_short"] | reg["gate_risk"]).reindex(led.index).fillna(False).to_numpy()
    for name, mask, mult in [("daily_short_half", daily_gate, 0.5),
                             ("daily_short_zero", daily_gate, 0.0),
                             ("daily_either_half", daily_either, 0.5)]:
        rr = np.where(mask, led["ret"].to_numpy() * mult, led["ret"].to_numpy())
        rr = pd.Series(rr, index=led.index)
        overlay[name] = {
            "gated_days": int(mask.sum()),
            "2021": float((1 + rr[rr.index.year == 2021]).prod() - 1),
            "2022": float((1 + rr[rr.index.year == 2022]).prod() - 1),
            "2021_2026": float((1 + rr).prod() - 1),
        }

    # Monthly IC from the frozen forecast file.  `ret` is the return of the
    # month labelled by `date`; this is the same series used in OOS_FREEZE.
    from scipy.stats import spearmanr
    f = pd.read_parquet(ROOT / "fiam/v4b/out/elasso/run_oos/forecastElasso_oos.parquet")
    f["date"] = pd.to_datetime(f.date)
    ic = {}
    for col in ["MaInf", "Ma1", "Ma36", "Ma60", "Ma120"]:
        vals = []
        for dd, gg in f.dropna(subset=["ret", col]).groupby("date"):
            if len(gg) > 20:
                vals.append((dd, float(spearmanr(gg[col], gg["ret"]).statistic)))
        s = pd.Series(dict(vals)).sort_index()
        ic[col] = {"mean": float(s.mean()),
                   "t": float(s.mean() / s.std(ddof=1) * np.sqrt(len(s))),
                   "by_year": {str(int(k)): float(v) for k, v in s.groupby(s.index.year).mean().items()},
                   "2021_01": float(s.get(pd.Timestamp("2021-01-31"), np.nan)),
                   "2021_02": float(s.get(pd.Timestamp("2021-02-28"), np.nan)),
                   "2021_03": float(s.get(pd.Timestamp("2021-03-31"), np.nan)),
                   "monthly": {str(k.date()): float(v) for k, v in s.items()}}

    # Invalid vs corrected 2026 NAV path.
    invalid = parse_nav(ROOT / "fiam/v4b/out/engine/nautilus_oos_invalid2026.log")
    corrected = parse_nav(ROOT / "fiam/v4b/out/engine/nautilus_oos_corrected_native_report_kill.log")
    inv_ret = invalid.pct_change().loc["2026-01-01":]
    cor_ret = corrected.pct_change().loc["2026-01-01":]
    compare = pd.concat([inv_ret.rename("invalid"), cor_ret.rename("corrected")], axis=1).dropna()

    # Top contributors from daily holdings and daily total returns.
    dd = pd.read_parquet(ROOT / "data/fiam_v1/daily_market_2026.parquet",
                         columns=["permno", "date", "total_return"],
                         filters=[("date", ">=", pd.Timestamp("2021-01-01")),
                                  ("date", "<=", pd.Timestamp("2026-08-31"))]).drop_duplicates(["permno", "date"])

    # Long/short contribution using prior-close weights and next-session total
    # return.  This is a sign/magnitude diagnostic; marked weights drift inside
    # the session, so the contributions are not an exact reconciliation.
    side_pos = pos.sort_values(["permno", "date"]).copy()
    side_pos["date_next"] = side_pos.groupby("permno")["date"].shift(-1)
    side = side_pos.merge(dd, left_on=["permno", "date_next"], right_on=["permno", "date"],
                          suffixes=("", "_r"), how="inner")
    side["contrib"] = side["w"] * side["total_return"]
    side["year"] = side["date_next"].dt.year
    side_year = {}
    for yy, g in side.groupby("year"):
        side_year[str(int(yy))] = {
            "long": float(g.loc[g["w"] > 0, "contrib"].sum()),
            "short": float(g.loc[g["w"] < 0, "contrib"].sum()),
            "total": float(g["contrib"].sum()),
            "avg_long_gross": float(g.groupby("date_next").apply(lambda x: x.loc[x.w > 0, "w"].sum()).mean()),
            "avg_short_gross": float(g.groupby("date_next").apply(lambda x: x.loc[x.w < 0, "w"].abs().sum()).mean()),
        }

    # Equal-weight forecast quintiles, gross of costs.  Q0 is the short tail,
    # Q4 the long tail; "ls" is Q4-Q0.
    fq = f.dropna(subset=["ret", "MaInf"]).copy()
    fq["q"] = fq.groupby("date")["MaInf"].transform(
        lambda z: pd.qcut(z, 5, labels=False, duplicates="drop"))
    q = fq.groupby(["date", "q"])["ret"].mean().unstack()
    q["ls"] = q[4] - q[0]
    q["year"] = q.index.year
    quint = {
        "by_year": {str(int(y)): {str(c): float(v) for c, v in row.items()}
                    for y, row in q.groupby("year").mean().iterrows()},
        "full_mean_monthly": {str(c): float(q[c].mean() / 100.0) for c in [0, 4, "ls"]},
        "ls_t_annualized": float(q["ls"].mean() / q["ls"].std(ddof=1) * np.sqrt(12)),
        "ls_negative_months": int((q["ls"] < 0).sum()),
        "months": int(len(q)),
        "first_months": {str(k.date()): {"short_q0": float(v[0] / 100.0),
                                         "long_q4": float(v[4] / 100.0),
                                         "ls": float(v["ls"] / 100.0)}
                         for k, v in q.loc["2021-01-31":"2021-03-31"].iterrows()},
        "q0_positive_months": int((q[0] > 0).sum()),
        "q4_positive_months": int((q[4] > 0).sum()),
    }

    m = pos[["date", "permno", "w"]].merge(dd, on=["date", "permno"], how="left")
    m["contrib"] = m["w"] * m["total_return"].fillna(0.0)
    top = {}
    for yy, g in m.groupby(m.date.dt.year):
        by = g.groupby("permno")["contrib"].sum().sort_values()
        top[str(int(yy))] = {"worst": {str(k): float(v) for k, v in by.head(5).items()},
                             "best": {str(k): float(v) for k, v in by.tail(5).iloc[::-1].items()}}

    breaches = pd.read_parquet(E3 / "breaches.parquet")
    br = breaches.groupby(["rule"]).size().to_dict() if len(breaches) else {}
    br_year = breaches.groupby([breaches.date.dt.year, "rule"]).size().unstack(fill_value=0)
    policy = pd.read_parquet(E3 / "policy_exposures.parquet")

    out = {
        "summary": summary,
        "headline": full,
        "parts": part,
        "years": years,
        "monthly": {"net": {str(k.date()): float(v) for k, v in monthly.items()},
                    "active": {str(k.date()): float(v) for k, v in monthly_active.items()},
                    "gross": {str(k.date()): float(v) for k, v in monthly_gross.items()},
                    "benchmark": {str(k.date()): float(v) for k, v in monthly_bench.items()},
                    "rolling12_ir": {"min": float(rolling.min()), "max": float(rolling.max()),
                                     "last": float(rolling.dropna().iloc[-1])}},
        "ff5": {"n": int(len(x)), "alpha_ann": float(coef[0] * 12),
                "beta": dict(zip(cols, map(float, coef[1:]))), "r2": float(r2)},
        "beta_sp500": beta,
        "march_2021": march,
        "regime_overlay": overlay,
        "ic": ic,
        "invalid_vs_corrected_2026": {
            "months": {str(k.date()): {"invalid": float(v.invalid), "corrected": float(v.corrected)}
                       for k, v in compare.iterrows()},
            "invalid_ytd_jan_jul": float((1 + inv_ret).prod() - 1),
            "corrected_ytd_jan_jul": float((1 + cor_ret).prod() - 1),
            "delta_pp_jan_jul": float(((1 + cor_ret).prod() - 1) - ((1 + inv_ret).prod() - 1)),
            "corrected_jan_aug": float((1 + led.loc["2026-01-01":"2026-08-31", "ret"]).prod() - 1),
        },
        "side_attribution": side_year,
        "quintiles": quint,
        "top_contributors": top,
        "breaches": {"total": int(len(breaches)), "by_rule": br,
                     "by_year": {str(int(k)): {str(c): int(v) for c, v in row.items() if v}
                                 for k, row in br_year.iterrows()}},
        "policy": {"max_abs_beta": float(policy["beta"].abs().max()),
                   "max_sector": float(policy["sector_max"].max()),
                   "violated_days": int(policy["violated"].fillna(True).sum()),
                   "days": int(len(policy))},
        "gate_months_2021_2026": {str(k.date()): bool(v) for k, v in gate["gate_short"].loc["2020-12-31":"2026-07-31"].items()},
    }
    (OUT / "analysis.json").write_text(json.dumps(out, indent=2, default=float) + "\n")
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
