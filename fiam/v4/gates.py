# The step 6 gates: six signals under Holm (protocol "Step 6 rules").

import hashlib
import json
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from fiam.v4 import agreement, clock, data, labels, ranks, sources
from fiam.v4.signals import (
    base,
    best_ideas,
    earnings_premium,
    edgar_flags,
    insiders,
    lazy_prices,
    options_flow,
    short_interest,
    syy,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out" / "v4" / "gates"
PROTOCOL = ROOT / "versions" / "v4" / "protocol.md"
CHAR_LIST = ROOT / "data" / "organisers" / "factor_char_list.csv"
# The stages in their order; each later one needs the earlier at HEAD.
STAGES = ("check", "power", "controls", "gates")
# The known-by check's formations (review E's months), no return read.
TIMING_MONTHS = pd.to_datetime(["2016-12-31", "2018-06-30", "2020-03-31"])
# Tables a signal reads by date, not by publication: never cut.
UNCUT = {"links", "panel", "labels"}
# The family of six, in build order; customer momentum failed its check.
SIGNALS = {
    "short_interest": short_interest,
    "red_flags": edgar_flags,
    "insiders": insiders,
    "lazy_prices": lazy_prices,
    "best_ideas": best_ideas,
}
FAILED = {"customer_momentum": "customer names right on 83 of 100 (bar 85); not built"}
FAMILY = len(SIGNALS) + len(FAILED)
# Two signals gated late (reading 18), Holm over 8 with the six.
LATE = {"options_flow": options_flow, "earnings_premium": earnings_premium}
# The six gates' results the late stage reuses: the run at fa169bf.
SIX = "fa169bf9301a"
# Holm step-down at 5% family-wise: 0.83%, 1%, 1.25%, 1.67%, 2.5%, 5%.
ALPHA = 0.05
HOLM = [ALPHA / (FAMILY - i) for i in range(FAMILY)]
# A month counts with 100 stocks carrying the signal; a gate needs 24.
MIN_STOCKS, MIN_MONTHS = 100, 24
# The simulated nulls: 100,000 series, seed 20261025, AR(1) burn-in 50.
NULL_SERIES, NULL_SEED, BURN, RHO_CAP, LAGS = 100_000, 20261025, 50, 0.9, 6
# Controls rerun (2026-10-26): 20 pilots, then 100 planted, 100 noise.
PILOT_SEEDS = range(20261500, 20261520)
POSITIVE_SEEDS, NEGATIVE_SEEDS = range(20261300, 20261400), range(20261400, 20261500)
# Bisection steps for the planted noise scale, from 0.01 to 100.
BISECT = 30
POSITIVE_PASS, NEGATIVE_MAX, CONTROL_MONTHS, NOISE_HOLD = 70, 10, 70, 12
Z80 = float(norm.ppf(0.8))
# Coverage bias: a |t| over 2 reruns the gate, uncovered stocks at 0.
COVERAGE_T = 2.0
# The power check uses formations 2015-2018 only (step 6 rules).
POWER_LAST = pd.Timestamp("2018-12-31")
# Ancillary windows end by 2020-12-31: SUE to 2020-08, flags to 2019-12.
SUE_LAST, FLAGS_LAST = pd.Timestamp("2020-08-31"), pd.Timestamp("2019-12-31")
LAST_DAY = clock.LAST_LABEL_DAY
FOUR_MONTHS, YEAR = pd.DateOffset(months=4), pd.DateOffset(months=12)


# The runner refuses an uncommitted tree; the commit dates the code.
def commit() -> str:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    if dirty:
        raise RuntimeError("commit and push the gate code first: the tree is not clean")
    # The remote dates the code: HEAD must sit on a pushed branch.
    pushed = subprocess.run(
        ["git", "branch", "-r", "--contains", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    if not pushed:
        raise RuntimeError("push the gate code first: no remote branch holds HEAD")
    head = ["git", "rev-parse", "HEAD"]
    return subprocess.run(head, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


# A stage's result file, one per commit, so every run stays logged.
def result_path(stage: str, head: str) -> Path:
    return OUT / f"{stage}_{head[:12]}.json"


# Each stage needs the earlier ones run at this commit and protocol.
def require(stage: str, head: str) -> None:
    if stage not in STAGES:
        raise SystemExit(f"unknown stage {stage}: check, timing, power, controls or gates")
    sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    for before in STAGES[1 : STAGES.index(stage)]:
        path = result_path(before, head)
        if not path.exists():
            raise SystemExit(f"run the {before} stage first at this commit ({path.name})")
        done = json.loads(path.read_text())
        if done["stamp"]["commit"] != head or done["stamp"]["protocol_sha256"] != sha:
            raise SystemExit(f"{path.name} is from another commit or protocol")
        if before == "controls" and not done["controls"]["controls_pass"]:
            raise SystemExit("a control failed: the gates do not run (leader 2026-10-25)")


# Every result file carries the commit, protocol and input hashes.
def stamp(head: str, seeds: dict) -> dict:
    tables = ["labels", "panel", "dsf", "crsp_daily", "crsp_monthly", "short_interest", "events"]
    tables += ["sec_insiders", "sections", "sec_13f", "sec_13f_reports", "sue", "links", "exits"]
    return {
        "commit": head,
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "input_cards_sha256": {t: data.card_sha(t) for t in tables},
        "char_list_sha256": hashlib.sha256(CHAR_LIST.read_bytes()).hexdigest(),
        "seeds": seeds,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# Each row's Newey-West t of its mean, 6 Bartlett lags (agreement.nw_t).
def nw_t_rows(y: np.ndarray, lags: int = LAGS) -> np.ndarray:
    n = y.shape[1]
    e = y - y.mean(axis=1, keepdims=True)
    long_run = (e * e).sum(axis=1) / n
    for j in range(1, lags + 1):
        long_run += 2 * (1 - j / (lags + 1)) * (e[:, j:] * e[:, :-j]).sum(axis=1) / n
    return y.mean(axis=1) / np.sqrt(long_run / n)


# Null t statistics at length n: iid, or AR(1) at rho (burn-in 50).
def null_t(n: int, rho: float = 0.0, series: int | None = None) -> np.ndarray:
    rng = np.random.default_rng(NULL_SEED)
    shocks = rng.standard_normal((NULL_SERIES if series is None else series, n + BURN))
    if rho > 0:
        for k in range(1, n + BURN):
            shocks[:, k] += rho * shocks[:, k - 1]
    return nw_t_rows(shocks[:, BURN:])


# One-sided p, (k + 1)/(B + 1) of null t at or above t; no t gives 1.
def p_value(t: float, null: np.ndarray) -> float:
    if not np.isfinite(t):
        return 1.0
    return float(((null >= t).sum() + 1) / (len(null) + 1))


# The first-order autocorrelation of a demeaned series (textbook).
def autocorrelation(y: pd.Series) -> float:
    e = (y - y.mean()).to_numpy()
    if len(e) < 3 or not (e * e).sum() > 0:
        return 0.0
    return float((e[1:] * e[:-1]).sum() / (e * e).sum())


# An IC series' t, its AR(1) rho and both p-values; the larger counts.
def test_series(ic: pd.Series, nulls: dict | None = None) -> dict:
    ic = ic.dropna()
    n = len(ic)
    t = agreement.nw_t(ic)
    rho = float(np.clip(autocorrelation(ic), 0.0, RHO_CAP))
    nulls = {} if nulls is None else nulls
    if n not in nulls:
        nulls[n] = null_t(n)
    p_iid = p_value(t, nulls[n])
    p_ar = p_value(t, null_t(n, rho)) if rho > 0 else p_iid
    return {"months": n, "mean_ic": float(ic.mean()), "nw_t": float(t), "rho": rho,
            "p_iid": p_iid, "p_ar1": p_ar, "p": max(p_iid, p_ar)}  # fmt: skip


# Holm's step-down: pass while each sorted p clears its bar, then stop.
def holm(pvalues: dict, bars: list | None = None) -> dict:
    bars = HOLM if bars is None else bars
    order = sorted(pvalues, key=lambda k: pvalues[k])
    out, open_ = {}, True
    for i, name in enumerate(order):
        open_ = open_ and pvalues[name] <= bars[i]
        out[name] = {"p": pvalues[name], "bar": bars[i], "passes": bool(open_)}
    return out


# Each formation's month: universe, residual label, SYY-10 and the 147.
class Month:
    # The design every signal is orthogonalised on, ranked in the universe.
    def __init__(self, eom, lab: pd.DataFrame, chars: list[str]):
        self.eom = pd.Timestamp(eom)
        self.T = data.eom_session([self.eom]).iloc[0]
        ids = base.universe_at(self.eom)
        lab = lab[lab["eom"] == self.eom].set_index("permno")
        self.label = lab["resid_universe"].reindex(ids)
        p = data.table("panel", chars, where={"eom": (self.eom, self.eom)}).set_index("permno")
        data.assert_public_by(p["first_close"], self.T, "gate panel rows")
        x = pd.DataFrame({c: ranks.unit_rank(p[c].reindex(ids)) for c in chars}, index=ids)
        s = syy.at(self.eom).set_index("permno")["syy"].reindex(ids)
        x.insert(0, "syy", s)
        self.x = x.fillna(0.0)
        self.x.insert(0, "const", 1.0)
        self.ids = ids

    # A signal ranked in the universe, signed, then residualised.
    def residual(self, value: pd.Series, sign: int, zero_uncovered: bool = False) -> pd.Series:
        v = value.reindex(self.ids)
        have = v.notna()
        r = sign * ranks.unit_rank(v[have])
        x = self.x[have.to_numpy()]
        coef, *_ = np.linalg.lstsq(x.to_numpy(), r.to_numpy(), rcond=None)
        out = pd.Series(r.to_numpy() - x.to_numpy() @ coef, index=r.index)
        # The coverage rule: uncovered stocks at exactly 0 (step 6 rules).
        return out.reindex(self.ids).fillna(0.0) if zero_uncovered else out

    # Spearman IC of a residualised signal with a label, both present.
    def ic(self, score: pd.Series, label: pd.Series | None = None) -> float:
        label = self.label if label is None else label
        both = pd.concat([score, label.reindex(score.index)], axis=1).dropna()
        if len(both) < MIN_STOCKS:
            return float("nan")
        return float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank()))


# The one-month labels and the formations the gates run on (to 2020-10).
def months(chars: list[str]) -> list[Month]:
    cols = ["label", "resid_universe", "T", "me", "end", "available"]
    lab = sources.read("labels", cols, purpose="label")
    lab = lab[lab["horizon"] == 1]
    # Every label window ends by 2020-12-31 (step 6 rules: asserted).
    assert (lab[["end", "available"]] <= LAST_DAY).all().all()
    assert (lab["available_at"] <= sources.SEAL).all()
    return [Month(e, lab, chars) for e in labels.formations(1)]


# Each signal's values at every formation, built from registered tables.
def signal_values(eoms) -> tuple[dict, dict]:
    values, logs = {}, {}
    for name, module in SIGNALS.items():
        logs[name] = {}
        frame = module.build(eoms, logs[name])
        values[name] = {e: g.set_index("permno")["value"] for e, g in frame.groupby("eom")}
    return values, logs


# Qualifying months and coverage per signal: counts only, no return.
def check(eoms=None) -> dict:
    eoms = labels.formations(1) if eoms is None else eoms
    values, logs = signal_values(eoms)
    out = {}
    for name, by_month in values.items():
        counts = []
        for e in eoms:
            ids = base.universe_at(e)
            v = by_month.get(pd.Timestamp(e), pd.Series(dtype=float)).reindex(ids)
            counts.append(int(v.notna().sum()))
        qualifying = sum(c >= MIN_STOCKS for c in counts)
        out[name] = {"build": logs[name], "stocks_per_month_min": min(counts),
                     "stocks_per_month_median": float(np.median(counts)),
                     "qualifying_months": qualifying,
                     "fails_for_coverage": qualifying < MIN_MONTHS}  # fmt: skip
    return out


# Readers that see only rows public by T, as a later 4/A was unknown.
@contextmanager
def known_by(T):
    table, parts = data.table, sources.read_parts
    close = data.calendar().loc[T]

    # A frame cut to its rows public by T, with later 4/As unknown.
    def cut(f: pd.DataFrame) -> pd.DataFrame:
        if "first_close" in f.columns:
            f = f[f["first_close"] <= T]
        if "superseded_at" in f.columns:
            f = f.assign(superseded_at=f["superseded_at"].where(f["superseded_at"] < close))
        return f

    data.table = lambda name, *a, **k: (
        table(name, *a, **k) if name in UNCUT else cut(table(name, *a, **k))
    )
    sources.read_parts = lambda *a, **k: (cut(f) for f in parts(*a, **k))
    try:
        yield
    finally:
        data.table, sources.read_parts = table, parts


# Values that move when rows public after T are dropped: must be 0.
def timing(eoms=TIMING_MONTHS) -> dict:
    full, _ = signal_values(eoms)
    out = {}
    for e in pd.DatetimeIndex(eoms):
        with known_by(data.eom_session([e]).iloc[0]):
            cut, _ = signal_values([e])
        for name in SIGNALS:
            a = full[name].get(e, pd.Series(dtype=float)).rename("a")
            b = cut[name].get(e, pd.Series(dtype=float)).rename("b")
            j = pd.concat([a, b], axis=1)
            moved = ((j["a"] - j["b"]).abs() > 1e-12) | (j["a"].isna() != j["b"].isna())
            out[f"{e.date()} {name}"] = {"stocks": len(j), "moved": int(moved.sum())}
    return out


# One gate: monthly ICs, both p-values, IC by year (no coverage rerun).
def gate_series(ms: list[Month], by_month: dict, sign: int, zero: bool = False, lab=None):
    ic = {}
    for m in ms:
        v = by_month.get(m.eom, pd.Series(dtype=float)).reindex(m.ids)
        if v.notna().sum() < MIN_STOCKS:
            continue
        label = None if lab is None else lab.get(m.eom)
        ic[m.eom] = m.ic(m.residual(v, sign, zero), label)
    return pd.Series(ic).dropna()


# The PDF test on a gate's coverage set (PDF p11), as agreement does.
def coverage_test(ms: list[Month], by_month: dict) -> dict:
    have = set()
    for m in ms:
        v = by_month.get(m.eom, pd.Series(dtype=float)).reindex(m.ids)
        have |= {(p, m.eom.to_period("M")) for p in v.index[v.notna()]}
    return agreement.source_test(have, agreement.panel_months(), agreement.leavers())


# The label regression with a covered dummy, for the coverage rerun.
def covered_labels(ms: list[Month], by_month: dict) -> dict:
    lab = sources.read("labels", ["label", "T", "me"], purpose="label")
    lab = lab[lab["horizon"] == 1]
    flags = []
    for m in ms:
        v = by_month.get(m.eom, pd.Series(dtype=float)).reindex(m.ids)
        flags.append(pd.DataFrame({"permno": m.ids, "eom": m.eom,
                                   "covered": v.notna().astype(float).to_numpy()}))  # fmt: skip
    extra = pd.concat(flags).set_index(["permno", "eom"])[["covered"]]
    res = labels.residual(lab, "universe", extra=extra)
    return {e: g.set_index("permno")["resid"] for e, g in res.groupby("eom")}


# One gate with its coverage rule: its tests and the p that enters Holm.
def gate_one(ms: list[Month], by_month: dict, sign: int, nulls: dict) -> dict:
    series = gate_series(ms, by_month, sign)
    res = {"main": test_series(series, nulls) if len(series) >= MIN_MONTHS else None}
    res["ic_by_year"] = series.groupby(series.index.year).mean().round(5).to_dict()
    res["coverage"] = cov = coverage_test(ms, by_month)
    p = res["main"]["p"] if res["main"] else 1.0
    if abs(cov["gap_nw_t"]) > COVERAGE_T or abs(cov["gap_next_month_nw_t"]) > COVERAGE_T:
        lab = covered_labels(ms, by_month)
        rerun = gate_series(ms, by_month, sign, zero=True, lab=lab)
        res["coverage_rerun"] = test_series(rerun, nulls)
        p = max(p, res["coverage_rerun"]["p"])
    res["p_for_holm"] = p
    return res


# Every gate with its coverage rule, then Holm (run after the commit).
def run_gates(ms: list[Month], values: dict, nulls: dict) -> dict:
    out, pvalues = {}, {}
    for name, module in SIGNALS.items():
        res = gate_one(ms, values[name], module.SIGN, nulls)
        out[name], pvalues[name] = res, res["p_for_holm"]
    for name, why in FAILED.items():
        out[name], pvalues[name] = {"failed": why, "p_for_holm": 1.0}, 1.0
    return {"gates": out, "holm": holm(pvalues), "kiefer_vogelsang": fixed_b(len(ms)),
            "iid_nulls": null_record(nulls)}  # fmt: skip


# The late gates (reading 18): two signals, Holm over the six and them.
def late(ms: list[Month], nulls: dict) -> dict:
    six = json.loads(result_path("gates", SIX).read_text())["gates"]["gates"]
    pvalues = {name: res["p_for_holm"] for name, res in six.items()}
    out, logs = {}, {}
    for name, module in LATE.items():
        logs[name] = {}
        frame = module.build(labels.formations(1), logs[name])
        by_month = {e: g.set_index("permno")["value"] for e, g in frame.groupby("eom")}
        out[name] = gate_one(ms, by_month, module.SIGN, nulls)
        pvalues[name] = out[name]["p_for_holm"]
    size = len(pvalues)
    bars = [ALPHA / (size - i) for i in range(size)]
    # The original six alone, beside the eight, reported only (reading 20).
    six_only = holm({k: pvalues[k] for k in six})
    return {"gates": out, "six_from": SIX, "holm": holm(pvalues, bars),
            "holm_six_only": six_only, "build": logs}  # fmt: skip


# Each iid null's hash and cut-offs; the arrays are saved beside.
def null_record(nulls: dict) -> dict:
    return {int(n): {"sha256": hashlib.sha256(a.tobytes()).hexdigest(),
                     "cut_0_83pct": float(np.quantile(a, 1 - HOLM[0])),
                     "cut_5pct": float(np.quantile(a, 1 - ALPHA))}
            for n, a in nulls.items()}  # fmt: skip


# Ancillaries (K2), reported, never gating: next SUE, later red flags.
def ancillaries(ms: list[Month], values: dict) -> dict:
    sue = sources.read("sue", ["sue", "announced", "end", "filed"], purpose="label")
    assert (sue["available_at"] <= sources.SEAL).all()
    ev = data.table("events", ["red_flag"])
    ev = ev[ev["red_flag"].astype(bool)]
    out = {}
    for name, module in SIGNALS.items():
        ic = {}
        for m in ms:
            v = values[name].get(m.eom, pd.Series(dtype=float)).reindex(m.ids)
            if v.notna().sum() < MIN_STOCKS:
                continue
            if name == "lazy_prices":
                # A red flag in the 12 months after T; formations to 2019-12.
                if m.eom > FLAGS_LAST:
                    continue
                outcome = later_flags(ev, m.T, m.ids)
            else:
                # The next quarter announced within 4 months of T, to 2020-08.
                if m.eom > SUE_LAST:
                    continue
                outcome = next_sue(sue, m.T)
            ic[m.eom] = m.ic(m.residual(v, module.SIGN), outcome)
        series = pd.Series(ic).dropna()
        res = test_series(series) if len(series) >= MIN_MONTHS else {"months": len(series)}
        out[name] = res | {
            "ic_by_year": series.groupby(series.index.year).mean().round(5).to_dict()
        }
    return out


# 1 with a red-flag 8-K public in the 12 months after T, else 0.
def later_flags(ev: pd.DataFrame, T, ids) -> pd.Series:
    assert T + YEAR <= LAST_DAY, "a red-flag window passes 2020-12-31"
    later = ev[(ev["first_close"] > T) & (ev["first_close"] <= T + YEAR)]
    return pd.Series(np.isin(ids, later["permno"]).astype(float), index=ids)


# The next SUE announced within 4 months after T; the earlier quarter.
def next_sue(sue: pd.DataFrame, T) -> pd.Series:
    assert T + FOUR_MONTHS <= LAST_DAY, "an SUE window passes 2020-12-31"
    nxt = sue[(sue["announced"] > T) & (sue["announced"] <= T + FOUR_MONTHS)]
    nxt = nxt.sort_values(["announced", "end"], kind="stable").drop_duplicates("permno")
    return nxt.set_index("permno")["sue"]


# Kiefer-Vogelsang fixed-b critical values, b = 7/N, reported beside.
def fixed_b(n: int, steps: int = 1000, reps: int = 10_000) -> dict:
    lags = max(int(round(7 / n * steps)) - 1, 1)
    rng = np.random.default_rng(NULL_SEED)
    t = nw_t_rows(rng.standard_normal((reps, steps)), lags)
    return {"b": round(7 / n, 4), "cv_5pct": float(np.quantile(t, 0.95)),
            "cv_0_83pct": float(np.quantile(t, 1 - HOLM[0]))}  # fmt: skip


# Power: the smallest mean IC each gate detects at 80% (report only).
def power(ms: list[Month], values: dict, chars: list[str], nulls: dict) -> dict:
    early = [m for m in ms if m.eom <= POWER_LAST]
    out = {}
    for name, module in SIGNALS.items():
        ics = {c: [] for c in chars}
        for m in early:
            v = values[name].get(m.eom, pd.Series(dtype=float)).reindex(m.ids)
            have = v.notna().to_numpy()
            if have.sum() < MIN_STOCKS:
                continue
            for c, ic in loo_ics(m, have, chars).items():
                ics[c].append(ic)
        sd = [lrsd(pd.Series(v).dropna()) for v in ics.values() if len(v) >= MIN_MONTHS]
        sigma = float(np.median(sd))
        n = int(sum(values[name].get(m.eom, pd.Series(dtype=float)).reindex(m.ids).notna().sum()
                    >= MIN_STOCKS for m in ms))  # fmt: skip
        if n not in nulls:
            nulls[n] = null_t(n)
        out[name] = {"sigma": sigma, "months": n}
        for alpha in (HOLM[0], ALPHA):
            c = float(np.quantile(nulls[n], 1 - alpha))
            out[name][f"mde_at_{alpha:.4f}"] = (c + Z80) * sigma / np.sqrt(n)
    return out | {"iid_nulls": null_record(nulls)}


# Each column's residual on all the others: X (X'X)^-1 / its diagonal.
def loo_residuals(x: np.ndarray) -> np.ndarray:
    inv = np.linalg.pinv(x.T @ x)
    return (x @ inv) / np.diag(inv)


# Each characteristic's residual IC on SYY-10 and the other 146.
def loo_ics(m: Month, have: np.ndarray, chars: list[str]) -> dict:
    loo = loo_residuals(m.x[have].to_numpy())
    label = m.label[have].to_numpy()
    out = {}
    for c in chars:
        j = m.x.columns.get_loc(c)
        both = pd.DataFrame({"s": loo[:, j], "y": label}).dropna()
        out[c] = both["s"].rank().corr(both["y"].rank())
    return out


# A monthly series' Newey-West long-run standard deviation (6 lags).
def lrsd(y: pd.Series) -> float:
    a = y.to_numpy()[None, :]
    e = a - a.mean()
    n = a.shape[1]
    lr = (e * e).sum() / n
    for j in range(1, LAGS + 1):
        lr += 2 * (1 - j / (LAGS + 1)) * (e[:, j:] * e[:, :-j]).sum() / n
    return float(np.sqrt(lr))


# A planted series through the gate machinery: ranked, residualised, IC.
def planted_ic(ms: list[Month], scores: dict) -> pd.Series:
    out = {}
    for m in ms:
        s = scores.get(m.eom)
        if s is not None:
            out[m.eom] = m.ic(m.residual(s, 1))
    return pd.Series(out).dropna()


# The positive control's scores: the label's rank plus scaled noise.
def planted(ms: list[Month], k: float, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for m in ms:
        y = m.label.dropna()
        out[m.eom] = ranks.unit_rank(y) + k * pd.Series(rng.standard_normal(len(y)), index=y.index)
    return out


# The noise control: a per-stock draw held 12 months, then redrawn.
def noise(ms: list[Month], seed: int) -> dict:
    rng, draws, out = np.random.default_rng(seed), {}, {}
    for i, m in enumerate(ms):
        block = i // NOISE_HOLD
        for p in m.ids:
            if (p, block) not in draws:
                draws[(p, block)] = rng.standard_normal()
        out[m.eom] = pd.Series([draws[(p, block)] for p in m.ids], index=m.ids)
    return out


# Both controls; either failing stops the gates (leader 2026-10-25).
def controls(ms: list[Month], nulls: dict) -> dict:
    n = CONTROL_MONTHS
    if n not in nulls:
        nulls[n] = null_t(n)
    c = float(np.quantile(nulls[n], 1 - HOLM[0]))

    # The pilots' mean IC and IC sd, averaged so no one seed's luck sets k.
    def pooled(k):
        ics = [planted_ic(ms, planted(ms, k, s)) for s in PILOT_SEEDS]
        sd = float(np.mean([ic.std(ddof=1) for ic in ics]))
        return float(np.mean([ic.mean() for ic in ics])), sd, len(ics[0])

    # The pooled mean IC less the detectable target at the pooled sd.
    def gap(k):
        mean, sd, months = pooled(k)
        return mean - (c + Z80) * sd / np.sqrt(months)

    lo, hi = 0.01, 100.0
    for _ in range(BISECT):
        mid = np.sqrt(lo * hi)
        lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
    k = float(np.sqrt(lo * hi))
    pilot_mean, pilot_sd, _ = pooled(k)
    pos = [test_series(planted_ic(ms, planted(ms, k, s)), nulls)["p"] for s in POSITIVE_SEEDS]
    neg = [test_series(planted_ic(ms, noise(ms, s)), nulls)["p"] for s in NEGATIVE_SEEDS]
    passed = int(sum(p <= HOLM[0] for p in pos))
    false = int(sum(p <= ALPHA for p in neg))
    return {"noise_scale": k, "pilot_mean_ic": pilot_mean, "pilot_ic_sd": pilot_sd,
            "positive_passes_at_0_83pct": passed, "positive_bar": POSITIVE_PASS,
            "negative_passes_at_5pct": false, "negative_bar": NEGATIVE_MAX,
            "controls_pass": passed >= POSITIVE_PASS and false <= NEGATIVE_MAX,
            "iid_nulls": null_record(nulls)}  # fmt: skip


# Context only, never a pass condition: short-term reversal (Jegadeesh).
def reversal(ms: list[Month], chars: list[str]) -> dict:
    ic = {}
    for m in ms:
        x = m.x.drop(columns=["ret_1_0"]).to_numpy()
        r = -m.x["ret_1_0"].to_numpy()
        coef, *_ = np.linalg.lstsq(x, r, rcond=None)
        ic[m.eom] = m.ic(pd.Series(r - x @ coef, index=m.ids))
    return test_series(pd.Series(ic))


# Writes one stage's result with its stamp to out/v4/gates/.
def write(stage: str, result: dict, head: str, seeds: dict, nulls: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, a in nulls.items():
        np.save(OUT / f"null_iid_N{n}.npy", a)
    path = result_path(stage, head)
    path.write_text(json.dumps({"stamp": stamp(head, seeds), stage: result}, indent=1,
                               default=str))  # fmt: skip
    return path


# python -m fiam.v4.gates check|timing|power|controls|gates|late
if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "check"
    if stage == "check":
        print(json.dumps(check(), indent=1, default=str))
        sys.exit(0)
    if stage == "timing":
        print(json.dumps(timing(), indent=1))
        sys.exit(0)
    head = commit()
    # The late stage reuses fa169bf's controls; each stage runs once.
    if stage == "late":
        if result_path("late", head).exists():
            raise SystemExit("the late gates ran at this commit")
    else:
        require(stage, head)
    chars = sources.characteristics()
    ms = months(chars)
    seeds = {"null": NULL_SEED, "pilot": [PILOT_SEEDS.start, PILOT_SEEDS.stop - 1],
             "positive": [POSITIVE_SEEDS.start, POSITIVE_SEEDS.stop - 1],
             "negative": [NEGATIVE_SEEDS.start, NEGATIVE_SEEDS.stop - 1]}  # fmt: skip
    nulls: dict = {}
    if stage == "late":
        print(write("late", late(ms, nulls), head, seeds, nulls))
        sys.exit(0)
    if stage == "controls":
        print(write("controls", controls(ms, nulls), head, seeds, nulls))
        sys.exit(0)
    values, logs = signal_values(labels.formations(1))
    if stage == "power":
        print(write("power", power(ms, values, chars, nulls), head, seeds, nulls))
    elif stage == "gates":
        result = run_gates(ms, values, nulls)
        result |= {"build": logs, "reversal_context": reversal(ms, chars)}
        result["ancillaries"] = ancillaries(ms, values)
        print(write("gates", result, head, seeds, nulls))
