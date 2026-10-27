# In-sample what-if books on 2021-2026, one setting changed at a time.

import json
import shutil
import sys
from dataclasses import fields, replace

import numpy as np
import pandas as pd

from fiam.vfinal import data, final, headline, sources, universe
from fiam.vfinal import inputs as engine
from fiam.vfinal.construct import book, exam, optimizer
from fiam.vfinal.construct import inputs as construct
from fiam.vfinal.report import table_9_1

LABEL = "In-sample what-if: chosen with 2021-2026 visible, not the strategy."
# Every variant starts from the quarterly forecasts and loose limits.
BASE_RUN = {"cadence": "quarterly", "limits": "loose"}
VARIANTS = {
    "speed_0.2": {"speed": 0.2},
    "speed_0.5": {"speed": 0.5},
    "names_220": {"names_max": 220},
    "names_480": {"names_max": 480},
    "budget_half": {"cost_budget": 0.5},
    "budget_double": {"cost_budget": 2.0},
    "lambda_half": {"risk_lambda": 0.5},
    "lambda_double": {"risk_lambda": 2.0},
    "yearly_refits": {"cadence": "yearly"},
    "budget_none": {"cost_budget": None},
    "sectors_wide": {"sector_band": 0.10},
    "styles_free": {"style_cap": 2.0},
    "lowvol_alpha": {"alpha_vol": "divide"},
    "highvol_alpha": {"alpha_vol": "multiply"},
    "ivol_free": {"free_styles": ("high_ivol",)},
    "vol_reliability": {"vol_reliability": True},
    "stress_cov": {"stress": True},
    "andrew_package": {"alpha_vol": "multiply", "stress": True},
    "cap_3bn": {"entry_musd": 3000.0, "hold_musd": 2500.0},
}
# The volatility measure that splits each formation into thirds.
VOL = "ivol_capm_252d"
# Settings a variant scales by its factor rather than replaces.
SCALED = ("cost_budget", "risk_lambda")
SETTINGS = {f.name for f in fields(optimizer.Settings)}
OUT = headline.BASE / "whatif"
# The 23-row lines the summary keeps for each variant.
KEEP = (1, 3, 4, 8, 11, 21, 22, 23)


# One formation's settings with a variant's changes applied.
def varied(s: optimizer.Settings, change: dict) -> optimizer.Settings:
    kw = {}
    for k, v in change.items():
        if k not in SETTINGS:
            continue
        old = getattr(s, k)
        if k not in SCALED or v is None:
            kw[k] = v
        elif old is not None:
            kw[k] = old * v
    return replace(s, **kw)


# The design's settings with the headline changes, then the variant's.
def install(change: dict, loose: bool, forecasts_file=None) -> None:
    headline.install_settings(loose)
    frozen = exam.settings_for

    # Each formation's headline settings, then varied.
    def settings_for(k, s):
        at = frozen(k, s)
        return lambda eom, x, cap: varied(at(eom, x, cap), change)

    exam.settings_for = settings_for
    if "alpha_vol" in change:
        by_vol(change["alpha_vol"])
    if "free_styles" in change:
        k = headline.design()[0]
        z, cap, held = exam.DESIGNS[k]
        exam.DESIGNS[k] = (z, cap, tuple(h for h in held if h not in change["free_styles"]))
    if change.get("vol_reliability"):
        install_reliability(forecasts_file)
    if change.get("stress"):
        install_stress()
    # New names from the entry cap, held ones kept to the hold cap.
    if "entry_musd" in change:
        universe.ENTRY_MUSD = change["entry_musd"]
        universe.HOLD_MUSD = change["hold_musd"]


# Alpha divided or multiplied by each name's volatility, then aligned.
def by_vol(how: str) -> None:
    frozen = book.align

    # The scaled alpha, then the run's own alignment.
    def align(alpha, x, neutral=()):
        vol = (x["sigma_d"] / x["sigma_d"].median()).fillna(1.0)
        if how == "divide":
            return frozen(alpha / vol.clip(0.2, 5.0), x, neutral)
        return frozen(alpha * vol, x, neutral)

    book.align = align


# Each row's volatility third within its formation: 0 calm, 2 volatile.
def thirds(frame: pd.DataFrame) -> pd.Series:
    pct = frame.groupby("eom")["vol"].rank(pct=True)
    return (pct * 3).clip(upper=2.999).fillna(1.0).astype(int)


# Past monthly IC of the forecast in each third, with its clock.
def third_ics(f: pd.DataFrame, labels: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    m = f.merge(vol, on=["permno", "eom"]).merge(labels, on=["permno", "eom"])
    m = m.dropna(subset=["z", "vol", "label"])
    m = m.assign(third=thirds(m))
    ic = m.groupby(["eom", "third"]).apply(lambda g: g["z"].rank().corr(g["label"].rank()))
    public = m.groupby("eom")["public"].max().rename("public")
    return ic.rename("ic").reset_index().merge(public.reset_index(), on="eom")


# Each third's multiplier at a close, from months public by then only.
def multipliers(ics: pd.DataFrame, T, n0: int = 12, warm: int = 12) -> list[float]:
    past = ics[ics["public"] <= T]
    n = past["eom"].nunique()
    k = past.groupby("third")["ic"].mean().reindex([0, 1, 2])
    if n < warm or k.isna().any():
        return [1.0, 1.0, 1.0]
    shrunk = (n * k + n0 * k.mean()) / (n + n0)
    if shrunk.mean() <= 0:
        return [1.0, 1.0, 1.0]
    return (shrunk / shrunk.mean()).clip(0.5, 1.5).tolist()


# Alpha times its third's past reliability, in the run's own mode.
def install_reliability(forecasts_file) -> None:
    frozen, cache = book.align, {}

    # The scaled alpha, then the run's own alignment.
    def align(alpha, x, neutral=()):
        if not cache:
            f = pd.read_parquet(forecasts_file, columns=["permno", "eom", "z"])
            lab = sources.read("labels", ["resid_rank_universe", "month_available"],
                               purpose="label")  # fmt: skip
            lab = lab[lab["horizon"] == 1].rename(
                columns={"resid_rank_universe": "label", "month_available": "public"}
            )
            span = (f["eom"].min(), f["eom"].max())
            vol = data.table("panel", [VOL], where={"eom": span}).rename(columns={VOL: "vol"})
            vol = vol[["permno", "eom", "vol"]]
            cache.update({"f": f, "vol": vol, "ics": third_ics(f, lab[["permno", "eom", "label",
                                                                 "public"]], vol)})  # fmt: skip
        T = x["T"].iloc[0]
        eom = T + pd.offsets.MonthEnd(0)
        now = cache["f"][cache["f"]["eom"] == eom].merge(cache["vol"], on=["permno", "eom"])
        third = pd.Series(thirds(now).to_numpy(), index=now["permno"]).reindex(x.index).fillna(1)
        m = np.asarray(multipliers(cache["ics"], T))[third.astype(int).to_numpy()]
        return frozen(alpha * m, x, neutral)

    book.align = align


# Share of the 21 sessions before a close with stressed volatility.
def stress_share(market: pd.Series, T, window: int = 21) -> float:
    rv = market.rolling(21).std()
    flag = (rv > rv.expanding().median().shift(1)).astype(float)
    past = flag[flag.index < T].tail(window)
    return float(past.mean()) if len(past) else 0.0


# A matrix made symmetric with every eigenvalue at least a tiny floor.
def definite(m: np.ndarray) -> np.ndarray:
    m = (m + m.T) / 2
    w, v = np.linalg.eigh(m)
    w = np.clip(w, max(w.max(), 1e-12) * 1e-9, None)
    return (v * w) @ v.T


# A covariance with vols times 1.5 and correlations halfway to +-1.
def stressed(cov: pd.DataFrame) -> pd.DataFrame:
    sd = np.sqrt(np.clip(np.diag(cov.to_numpy()), 0.0, None))
    safe = np.where(sd > 0, sd, 1.0)
    corr = cov.to_numpy() / np.outer(safe, safe)
    corr = corr + 0.5 * (np.sign(corr) - corr)
    np.fill_diagonal(corr, 1.0)
    corr = definite(corr)
    d = np.sqrt(np.diag(corr))
    corr = corr / np.outer(d, d)
    out = definite(corr * np.outer(1.5 * sd, 1.5 * sd))
    return pd.DataFrame(out, index=cov.index, columns=cov.columns)


# The optimiser's factor risk mixed toward stress by the recent share.
def install_stress() -> None:
    frozen, cache = book.month, {}

    # The original month, its covariance then mixed for the optimiser only.
    def month(eom, *args, **kw):
        x, alpha, loadings, cov, spec = frozen(eom, *args, **kw)
        if not cache:
            last = final.END if sources.unsealed() else headline.SEALED_LAST
            days = data.calendar().index
            days = days[(days >= pd.Timestamp("2000-01-03")) & (days <= last)]
            cache["market"] = data.market_daily(days)
        p = stress_share(cache["market"], x["T"].iloc[0])
        mixed = definite((1 - p) * cov.to_numpy() + p * stressed(cov).to_numpy())
        return x, alpha, loadings, pd.DataFrame(mixed, cov.index, cov.columns), spec

    book.month = month


# The report's table given the PDF's monthly bill.
def install_report() -> None:
    construct.sp500 = engine.sp500
    frozen = table_9_1.table

    # The original table given the monthly bill.
    def table(daily, *args, **kw):
        bill = headline.monthly_rate(data.rf_daily(daily.index))
        return frozen(daily, *args, rf_monthly=bill, **kw)

    table_9_1.table = table


# One variant's book and 23 rows in its own folder, labelled in-sample.
def run(name: str, head: str) -> dict:
    change = VARIANTS[name]
    cadence = change.get("cadence", BASE_RUN["cadence"])
    limits = change.get("limits", BASE_RUN["limits"])
    final.OUT = OUT / name
    final.OUT.mkdir(parents=True, exist_ok=True)
    (final.OUT / "LABEL.txt").write_text(LABEL + "\n")
    file = headline.where("forecasts", (cadence,), head, "parquet")
    shutil.copyfile(file, final.path("forecasts", head, "parquet"))
    cache = headline.BASE / f"factor_returns_to_{final.LAST:%Y-%m}.parquet"
    if cache.exists():
        shutil.copyfile(cache, final.OUT / cache.name)
    scale = headline.scale_of(pd.read_parquet(file))
    install(change, limits == "loose", file)
    install_report()
    frozen = final.Context
    final.Context = lambda f, _, z, neutral=(): frozen(f, scale, z, neutral)
    with final.opened():
        made = final.final_book(head)
        final.path("book", head).write_text(json.dumps(made, indent=1, default=str))
        made |= final.report(head)
    out = {"label": LABEL, "variant": name, "change": change, "cadence": cadence,
           "limits": limits, "alpha_scale": scale} | made  # fmt: skip
    final.path("whatif", head).write_text(json.dumps(out, indent=1, default=str))
    return out


# One variant on 2017-2020, blind and scored as the exam, with its rule.
def early(name: str, head: str) -> dict:
    change = VARIANTS[name]
    cadence = change.get("cadence", BASE_RUN["cadence"])
    limits = change.get("limits", BASE_RUN["limits"])
    k, s = headline.design()
    final.OUT = OUT / name
    final.OUT.mkdir(parents=True, exist_ok=True)
    file = headline.where("forecasts", (cadence,), head, "parquet")
    install(change, limits == "loose", file)
    z, _, neutral = exam.DESIGNS[k]
    book.FORECASTS = file
    with headline.sealed():
        got = exam.design(exam.settings_for(k, s), z, neutral=neutral)
    got.pop("plans")
    got.pop("daily").to_parquet(final.OUT / f"early_daily_{head[:12]}.parquet")
    bar = json.loads(headline.where("early", (cadence, limits), head).read_text())["ir"]
    passes = got["breach_days"] == 0 and got["ir"] > bar
    out = {"label": LABEL, "variant": name, "change": change, "rule_ir": bar,
           "passes": passes} | got  # fmt: skip
    (final.OUT / f"early_{head[:12]}.json").write_text(json.dumps(out, indent=1, default=str))
    return out


# Every finished variant's key rows in one table, written to the folder.
def summary(head: str) -> pd.DataFrame:
    rows = []
    for name in VARIANTS:
        table = OUT / name / f"table_9_1_{head[:12]}.csv"
        if table.exists():
            t = pd.read_csv(table)
            t = t[t["row"].isin(KEEP)].set_index("name")["strategy"]
            rows.append(t.rename(name))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / f"summary_{head[:12]}.csv")
    return out


# python -m fiam.vfinal.whatif <variant> <commit> [early] | summary
if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (2, 3) or args[0] not in (*VARIANTS, "summary"):
        raise SystemExit(
            "uv run python -m fiam.vfinal.whatif <variant> <commit> [early] | summary <commit>"
        )
    if args[0] == "summary":
        print(summary(args[1]).to_string())
    elif args[2:] == ["early"]:
        got = early(args[0], args[1])
        print(json.dumps({k: got[k] for k in ("variant", "ir", "rule_ir", "passes")}, default=str))
    else:
        got = run(args[0], args[1])
        print(json.dumps({k: got[k] for k in ("variant", "change", "breach_days")}, default=str))
