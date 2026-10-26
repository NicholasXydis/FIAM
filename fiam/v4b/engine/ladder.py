# Validation ladder E0-E3 at $1bn in the daily simulator (R§8).
#
# Formations are the judge window eom 2016-12..2020-11, monthly. Each step
# builds target books with engine/optimize.py (cached to out/engine/), runs
# them through engine/sim.py on CRSP daily data, checks the executed books
# with engine/checker.py, and reports net IR against the mandate benchmark
# (TB3MS + 4%). Promotion gates are R§8's: delta net IR > 0, paired
# block-bootstrap 90% CI on monthly active returns excluding 0, and
# delta IR >= 0.15 for added-complexity steps. Ma1 vs MaInf (D6/D7) is the
# single E2 trial, settled here on net IR. N comes from the hurdle formula
# with the frozen MaInf IC and E2's measured costs - never an IR race.

import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.elasso import forecaster
from fiam.v4b.engine import borrow, checker, fallback, inputs, optimize, sim
from fiam.v4b.engine.mandate import Final
from fiam.v4b.engine.mandate import load as load_mandate
from fiam.v4b.engine.reconcile import monthly_reference
from fiam.v4b.forecast import data, evaluate, run
from fiam.v4b.risk import covariance, enhanced, model

OUT = Path(__file__).resolve().parents[1] / "out" / "engine"
WINDOW = (pd.Timestamp("2016-12-31"), pd.Timestamp("2020-11-30"))
FROZEN_IC = 0.030657265036583684  # MaInf held-out IC, out/elasso/report.json
GATE_FLOOR = 0.15


def _source_identity():
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for folder in ("engine", "risk", "elasso"):
        for path in sorted((root / folder).glob("*.py")):
            digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


# Capture the source that this interpreter actually imported. Reading files
# later could incorrectly bless an old in-memory solve after a source edit.
SOURCE_IDENTITY = _source_identity()


# Ladder steps (R§8 table); E2 runs twice (MaInf, then the Ma1 trial).
def steps(n_e3: int = 300, winner: str = "Elasso_MaInf") -> dict[str, optimize.Step]:
    base = dict(support="greedy", bands=True, borrow_term=True, names=300)
    return {
        "E0": optimize.Step("E0", support="rank", bands=False, borrow_term=False, names=300),
        "E1": optimize.Step("E1", **base),
        "E2": optimize.Step("E2", uncertainty=True, **base),
        "E2_Ma1": optimize.Step("E2_Ma1", column="Elasso_Ma1", uncertainty=True, **base),
        "E3": optimize.Step(
            "E3",
            column=winner,
            uncertainty=True,
            trade_costs=True,
            incumbent_credit=True,
            support="greedy",
            bands=True,
            borrow_term=True,
            names=n_e3,
        ),
        # E5 (user, 2026-10-26): max return - costs, min vol (enhanced risk +
        # direction-aware jump variance), min beta (penalty in the hard band),
        # gross capped rather than forced.
        "E5": optimize.Step(
            "E5",
            column=winner,
            uncertainty=True,
            trade_costs=True,
            incumbent_credit=True,
            jump_var=True,
            beta_penalty=True,
            gross_cap=True,
            vol_target=True,
            support="greedy",
            bands=True,
            borrow_term=True,
            names=n_e3,
        ),
        # E6 two-step (D18): HHRZ decile selection, then minimum risk/beta/costs
        # at mu'w >= 0.9 mu'w_ref (E5's risk, cost and band terms; no vol target,
        # gross 1.8 scaled down only above 12% predicted vol).
        **{
            name: optimize.Step(
                name,
                column=winner,
                support="twostep",
                weighting=wt,
                uncertainty=True,
                trade_costs=True,
                jump_var=True,
                beta_penalty=True,
                bands=True,
                borrow_term=True,
                names=n_e3,
            )
            for name, wt in (("E6", "vw"), ("E6_ew", "ew"))
        },
        # E3 plus the opposite-direction jump caps and budgets (D12).
        "E4": optimize.Step(
            "E4",
            column=winner,
            uncertainty=True,
            trade_costs=True,
            incumbent_credit=True,
            jump_risk=True,
            support="greedy",
            bands=True,
            borrow_term=True,
            names=n_e3,
        ),
    }


# Market frames + borrow grid + coverage, built once for every step.
class World:
    def __init__(
        self,
        m: Final,
        cut=None,
        window=None,
        daily_path=None,
        forecast_path=None,
    ):
        forecaster.verify_code()
        self.m = m
        self.cut = pd.Timestamp(cut or m.policy.blind_until)
        self.window = window or WINDOW
        self.daily_path = daily_path
        self.forecast_path = forecast_path
        self.rm = (enhanced.EnhancedRiskModel(cut=self.cut, beta_cal=m.policy.beta_calibration) if m.policy.risk_model == "enhanced"
                   else model.RiskModel(cut=self.cut))
        daily = inputs.daily("2016-01-01", blind_until=self.cut, path=daily_path)
        permnos = sorted(self.rm.exp["permno"].unique())
        self.market = inputs.market(
            daily, permnos, adv_window=m.policy.adv_window, vol_window=m.policy.vol_window
        )
        self.sessions = self.market["sessions"]
        self.rf = inputs.cash_rate(self.sessions)
        self.borrow = self._borrow_grid()
        self.coverage = self._coverage()
        self.jumps = self._jumps()
        self.mu = {
            c: forecaster.horizon_returns(
                m, c, age=0.0, hold=21.0, source=forecast_path
            )
            for c in (m.policy.forecaster_column, m.policy.forecaster_alternate)
        }

    # Annual borrow by permno at eom: short-interest tiers (engine/borrow.py)
    # or the flat case §7 alternative by carried eom market cap.
    def borrow_at(self, eom, permnos: pd.Index, me: pd.Series) -> pd.Series:
        if self.m.policy.borrow_schedule == "short_interest":
            return borrow.rates(eom, permnos)
        if self.m.policy.borrow_schedule != "flat":
            raise ValueError(self.m.policy.borrow_schedule)
        out = pd.Series(self.m.policy.borrow_flat_other, index=permnos)
        out.loc[me[me >= self.m.policy.borrow_large_musd].index.intersection(permnos)] = (
            self.m.policy.borrow_flat_large
        )
        return out

    # Daily borrow rates, each month's schedule carried until the next eom.
    def _borrow_grid(self) -> pd.DataFrame:
        cols = self.market["returns"].columns
        grid = pd.DataFrame(self.m.policy.borrow_flat_other, index=self.sessions, columns=cols)
        exp = self.rm.exp
        eoms = sorted(exp["eom"].unique())
        for i, eom in enumerate(eoms):
            start = self.sessions.searchsorted(pd.Timestamp(eom), side="right")
            end = (
                self.sessions.searchsorted(pd.Timestamp(eoms[i + 1]), side="right")
                if i + 1 < len(eoms)
                else len(self.sessions)
            )
            if start >= end:
                continue
            month = exp[exp["eom"] == eom].set_index("permno")["me"]
            live = grid.columns.intersection(month.index)
            grid.iloc[start:end, grid.columns.get_indexer(live)] = (
                self.borrow_at(eom, live, month).to_numpy()[None, :]
            )
        return grid

    # Next-month jump probabilities by (eom, permno), annual expanding refits
    # (risk/jumps.py); each year's model saw only labels ending by its December.
    def _jumps(self) -> pd.DataFrame:
        path = Path(__file__).resolve().parents[1] / "out" / "risk" / "jumps" / "probabilities.parquet"
        if not path.exists():
            return pd.DataFrame(columns=["p_y_up", "p_y_dn"])
        j = pd.read_parquet(path, columns=["permno", "eom", "p_y_up", "p_y_dn"])
        j["eom"] = pd.to_datetime(j["eom"]).astype("datetime64[ns]")
        return j[j["eom"] <= self.cut].dropna().set_index(["eom", "permno"]).sort_index()

    # Share of the 147 characteristics present, per (eom, permno).
    def _coverage(self) -> pd.Series:
        chars = data.characteristics()
        p = pd.read_parquet(
            data.PANEL,
            columns=["permno", "eom", *chars],
            filters=[
                ("eom", ">=", self.window[0] - pd.offsets.MonthEnd(2)),
                ("eom", "<=", self.window[1]),
            ],
        )
        p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
        share = p[chars].notna().mean(axis=1)
        return pd.Series(share.to_numpy(), index=pd.MultiIndex.from_frame(p[["eom", "permno"]]))

    # Last session on/before eom (the simulator's signal day for it).
    def signal_day(self, eom) -> pd.Timestamp:
        pos = self.sessions.searchsorted(pd.Timestamp(eom), side="right") - 1
        return self.sessions[pos]

    # One formation's optimizer inputs at eom.
    def formation(self, eom, column: str, w_pre: pd.Series, nav=None) -> optimize.Formation:
        eom = pd.Timestamp(eom)
        horizon = self.holding_sessions(eom)
        snap = self.rm.snapshot(eom, horizon=horizon)
        if self.m.policy.beta_source != "engine":  # D20: another market beta in B
            snap = self.beta_swap(snap, eom)
        if self.m.policy.beta_bands_extra:  # D21: further betas held in bands
            snap = self.beta_extra(snap, eom)
        mu = self.mu[column]
        mu_t = mu[mu["eom"] == eom].set_index("permno")["mu"] * forecaster.horizon_scale(
            0, horizon, forecaster.kappa_for(self.m, column)
        )
        t_sess = self.signal_day(eom)
        adv = self.market["adv"].loc[t_sess]
        spread = self.market["half_spread"].loc[t_sess]
        me = snap["month"]["me"]
        borrow = self.borrow_at(eom, snap["B"].index, me)
        try:
            cov = self.coverage.loc[eom]
        except KeyError:
            cov = pd.Series(0.5, index=snap["B"].index)
        try:
            jumps = self.jumps.loc[eom]
        except KeyError:
            jumps = pd.DataFrame(columns=["p_y_up", "p_y_dn"])
        return optimize.Formation(
            eom=eom,
            mu=mu_t,
            snap=snap,
            adv=adv,
            half_spread=spread,
            borrow=borrow,
            coverage=cov,
            w_pre=w_pre,
            nav=self.m.hard.nav0 if nav is None else nav,
            horizon=horizon,
            sigma=self.market["sigma"].loc[t_sess],
            price=self.market["price"].loc[t_sess],
            p_up=jumps["p_y_up"].astype(float),
            p_dn=jumps["p_y_dn"].astype(float),
            nyse_me=self.nyse_me(eom),
        )

    # All beta candidates on the snapshot's names at eom (risk/beta_candidates.py).
    def beta_candidates(self, snap: dict, eom) -> pd.DataFrame:
        from fiam.v4b.risk import beta as beta_mod
        from fiam.v4b.risk import beta_candidates as bc

        if getattr(self, "_excess", None) is None:
            self._excess = beta_mod.excess_wide(cut=self.rm.cut)
        excess, mk = self._excess
        return bc.at(self.rm, snap, excess, mk["mkt_rf"], eom, snap["B"].index)

    # The snapshot with policy.beta_source as its market beta (D20).
    def beta_swap(self, snap: dict, eom) -> dict:
        from fiam.v4b.risk import beta_candidates as bc

        cands = self.beta_candidates(snap, eom)
        return bc.apply(snap, cands[bc.SOURCES[self.m.policy.beta_source]])

    # The snapshot with the policy's extra betas (median-filled) as "beta_extra" (D21).
    def beta_extra(self, snap: dict, eom) -> dict:
        from fiam.v4b.risk import beta_candidates as bc

        cands = self.beta_candidates(snap, eom)
        extra = pd.DataFrame({b: bc.filled(cands[bc.SOURCES[b]]) for b in self.m.policy.beta_bands_extra})
        return snap | {"beta_extra": extra}

    # me ($m) of every NYSE name in the panel at eom (HHRZ breakpoints, E6).
    def nyse_me(self, eom) -> pd.Series:
        if getattr(self, "_nyse", None) is None:
            p = pd.read_parquet(data.PANEL, columns=["permno", "eom", "me", "crsp_nyse"],
                                filters=[("eom", "<=", self.cut), ("crsp_nyse", "==", 1)])
            p["eom"] = pd.to_datetime(p["eom"]).astype("datetime64[ns]")
            self._nyse = p.dropna(subset=["me"]).set_index(["eom", "permno"])["me"].sort_index()
        try:
            return self._nyse.loc[pd.Timestamp(eom)]
        except KeyError:
            return pd.Series(dtype=float)

    def holding_sessions(self, eom) -> int:
        start = self.sessions.get_loc(self.signal_day(eom))
        end = self.sessions.get_loc(self.signal_day(pd.Timestamp(eom) + pd.offsets.MonthEnd(1)))
        if end <= start:
            raise ValueError("next monthly review is outside the available calendar")
        return end - start

    def policy_inputs(self):
        if not hasattr(self, "_policy_inputs"):
            dated = (
                self.rm.exp[["eom", "permno", "sector", "size"]]
                .merge(self.rm.betas[["eom", "permno", "beta_hedge"]], on=["eom", "permno"])
                .rename(columns={"beta_hedge": "beta"})
            )
            widths = {}
            for e in dated["eom"].unique():
                if pd.Timestamp(e) < self.window[0]:
                    continue
                F1 = covariance.factor_cov(
                    self.rm.factors, pd.Timestamp(e) + pd.Timedelta(days=1), self.rm.factor_hl
                )
                widths[e] = 0.25 * optimize.SIGMA_REF / np.sqrt(F1.loc["size", "size"] * 252)
            dated["size_band"] = dated["eom"].map(widths)
            self._policy_inputs = dated
        return self._policy_inputs


def target_fingerprint(m: Final, step: optimize.Step) -> str:
    """Invalidate targets when construction, execution, inputs or policy changes."""
    digest = hashlib.sha256(
        json.dumps([dataclasses.asdict(m), dataclasses.asdict(step)], sort_keys=True).encode()
    )
    digest.update(SOURCE_IDENTITY.encode())
    for path in (
        inputs.DAILY,
        inputs.PANEL,
        inputs.TB3MS,
        data.CHARS,
        model.beta_mod.FF_DAILY,
        forecaster.run_dir(m) / "frozen.json",
        forecaster.run_dir(m) / "forecastElasso.parquet",
        Path(__file__).resolve().parents[1] / "out" / "risk" / "jumps" / "probabilities.parquet",
    ):
        stat = path.stat()
        digest.update(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


# Targets are formed inside the simulator using executed holdings and NAV.
def build_targets(world: World, step: optimize.Step, force: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"targets_{step.name}_n{step.names}"
    path, log_path = OUT / f"{tag}.parquet", OUT / f"{tag}_logs.json"
    meta_path = OUT / f"{tag}_meta.json"
    fingerprint = target_fingerprint(world.m, step)
    eoms = [
        e
        for e in sorted(world.rm.exp["eom"].unique())
        if world.window[0] <= pd.Timestamp(e) <= world.window[1]
    ]
    if (
        path.exists()
        and log_path.exists()
        and meta_path.exists()
        and not force
        and json.loads(meta_path.read_text()).get("fingerprint") == fingerprint
    ):
        frame = pd.read_parquet(path)
        targets = {world.signal_day(e): g.set_index("permno")["w"] for e, g in frame.groupby("eom")}
        return targets, json.loads(log_path.read_text())
    targets, logs = {}, []

    def builder(eom):
        def form(w_pre, nav):
            f = world.formation(eom, step.column, w_pre, nav=nav)
            w, log = optimize.build_book(f, world.m, step)
            logs.append(log | {"nav_at_signal": nav})
            if w is None:
                raise RuntimeError(f"{step.name} {eom}: no compliant book: {log}")
            targets[world.signal_day(eom)] = w
            print(
                f"{step.name} {pd.Timestamp(eom).date()}: {len(w)} names "
                f"gross {w.abs().sum():.3f} net {w.sum():+.4f} {log.get('status')}",
                flush=True,
            )
            return w

        return form

    run_books(world, {world.signal_day(e): builder(e) for e in eoms})
    frame = pd.concat(
        [
            w.rename("w").rename_axis("permno").reset_index().assign(eom=e)
            for e, w in zip(eoms, targets.values())
        ]
    )
    frame.to_parquet(path, index=False)
    log_path.write_text(json.dumps(logs, indent=1, default=run._plain) + "\n")
    meta_path.write_text(json.dumps({"fingerprint": fingerprint}) + "\n")
    return targets, logs


# Fallback books as simulator targets (same clock).
def fallback_targets(world: World) -> dict:
    panel = inputs.panel(fallback.COLUMNS, blind_until=world.cut)
    books = fallback.books(panel, world.m, world.m.hard.nav0)
    return {
        world.signal_day(e): w
        for e, w in books.items()
        if world.window[0] <= pd.Timestamp(e) <= world.window[1]
    }


# Runs target books through the $1bn daily simulator.
def run_books(
    world: World,
    targets: dict,
    adv_scale: float = 1.0,
    gross_scale: float = 1.0,
    spread_scale: float = 1.0,
):
    mk = world.market
    scaled = {d: w if callable(w) else w * gross_scale for d, w in targets.items()}
    market = sim.Market(
        returns=mk["returns"],
        adv=mk["adv"] * adv_scale,
        sigma=mk["sigma"],
        half_spread=mk["half_spread"] * spread_scale,
        borrow=world.borrow,
        rf=world.rf,
    )
    p = world.m.policy
    setup = sim.Setup(
        nav0=world.m.hard.nav0,
        participation=p.participation,
        impact_y=p.impact_y,
        stub_days=p.stub_days,
    )
    return sim.run(scaled, market, setup)


# OLS slope/intercept with Newey-West t (3 lags), for beta exhibits.
def ols_hac(y: pd.Series, x: pd.Series) -> dict:
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
    return {
        "alpha": float(coef[0]),
        "beta": float(coef[1]),
        "beta_se": float(se[1]),
        "beta_t": float(coef[1] / se[1]),
        "n": int(len(both)),
    }


# Monthly active returns (compounded daily strategy minus benchmark).
def monthly_active(ledger: pd.DataFrame, world: World) -> pd.Series:
    ledger = ledger.iloc[1:]
    bench = world.rf.reindex(ledger.index).fillna(0.0) + world.m.hard.premium / 252
    strat_m = (1 + ledger["ret"]).groupby(ledger.index.to_period("M")).prod() - 1
    bench_m = (1 + bench).groupby(bench.index.to_period("M")).prod() - 1
    out = strat_m - bench_m
    out.index = out.index.to_timestamp(how="end").normalize()
    return out


# Headline metrics for one simulator run (mandate §9 conventions).
def metrics(
    world: World,
    ledger: pd.DataFrame,
    positions: pd.DataFrame,
    enforce_policy: bool = False,
    panel: pd.DataFrame | None = None,
    breaches: pd.DataFrame | None = None,
    days: pd.DataFrame | None = None,
    policy_days: pd.DataFrame | None = None,
) -> dict:
    m = world.m
    problems = checker.reconcile(ledger.reset_index())
    signal_session = ledger.index[0]
    nav0 = ledger["nav"].iloc[0]
    nav_prev = ledger["nav"].shift(1).iloc[1:]
    ledger = ledger.iloc[1:]
    bench = world.rf.reindex(ledger.index).fillna(0.0) + m.hard.premium / 252
    active = ledger["ret"] - bench
    years = len(ledger) / 252
    # The first row is the cash state, not an earned return.
    calendar = ledger.index
    costs = ledger[["spread", "impact", "fees", "borrow"]].sum(axis=1)
    gross_ret = ledger["ret"] + (costs / nav_prev).fillna(0.0)
    gross_active = gross_ret - bench
    if panel is None:
        panel = inputs.panel(["me", "me_company"], blind_until=world.cut)
    if breaches is None or days is None:
        breaches, days = checker.check(positions, panel, m, ramp_days=5, sessions=calendar)
    if policy_days is None:
        policy_days = checker.policy_diagnostics(positions, world.policy_inputs(), m)
    policy_days = policy_days.reindex(calendar[5:])
    n_rebalances = positions.loc[positions["rebalance"], "date"].nunique()
    turn_mean = float(ledger["turnover"].sum() / n_rebalances) if n_rebalances else None
    sp_ret = inputs.market_returns(pd.DatetimeIndex([signal_session, *ledger.index]))
    sp_ret = sp_ret.reindex(ledger.index)
    excess = ledger["ret"] - world.rf.reindex(ledger.index).fillna(0.0)

    def ir(a):
        return float(a.mean() * 252 / (a.std(ddof=1) * np.sqrt(252))) if a.std() > 0 else None

    return {
        "net_ir_daily": ir(active),
        "gross_ir_daily": ir(gross_active),
        "active_ann_mean": float(active.mean() * 252),
        "active_ann_vol": float(active.std(ddof=1) * np.sqrt(252)),
        "cagr": float((ledger["nav"].iloc[-1] / nav0) ** (1 / years) - 1),
        "cost_pct_nav_yr": {
            c: float((ledger[c] / nav_prev).sum() / years)
            for c in ("spread", "impact", "fees", "borrow")
        },
        "turnover_per_rebalance": turn_mean,
        "turnover_annualised": turn_mean * 12 if turn_mean is not None else None,
        "turnover_sum_over_years": float(ledger["turnover"].sum() / years),
        "avg_names": float(days["names"].mean()),
        "min_names": int(days["names"].min()),
        "avg_gross": float(days["gross"].mean()),
        "max_gross": float(days["gross"].max()),
        "breaches": int(len(breaches)),
        "breach_rules": breaches.groupby("rule").size().to_dict() if len(breaches) else {},
        "policy_breach_days": int(policy_days["violated"].fillna(True).sum()),
        "policy_required": enforce_policy,
        "max_abs_hedge_beta": float(policy_days["beta"].abs().max()),
        "max_abs_sector": float(policy_days["sector_max"].max()),
        "reconcile": problems,
        "beta_sp500_daily": ols_hac(excess, sp_ret - world.rf.reindex(ledger.index).fillna(0.0)),
    }


# R§8 promotion gate of `new` over `old` on monthly active returns.
def paired_ir(new, old, periods_per_year=12, block=3, draws=2000):
    paired = pd.concat([new.rename("new"), old.rename("old")], axis=1).dropna()
    if len(paired) < 12:
        return None
    rng = np.random.default_rng(42)
    n = len(paired)
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block))))
    picks = ((starts[..., None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    values = paired.to_numpy()[picks]
    std = values.std(axis=1, ddof=1)
    ratio = np.divide(values.mean(axis=1), std, out=np.full_like(std, np.nan), where=std > 1e-12)
    delta = (ratio[:, 0] - ratio[:, 1]) * np.sqrt(periods_per_year)
    delta = delta[np.isfinite(delta)]
    if len(delta) < draws * 0.9:
        return None
    return {
        "n": n,
        "block": block,
        "draws": len(delta),
        "lo90": float(np.quantile(delta, 0.05)),
        "hi90": float(np.quantile(delta, 0.95)),
    }


def gate(
    old_m: dict,
    new_m: dict,
    old_monthly: pd.Series,
    new_monthly: pd.Series,
    old_daily=None,
    new_daily=None,
    floor=GATE_FLOOR,
) -> dict:
    d_ir = new_m["net_ir_daily"] - old_m["net_ir_daily"]
    paired = evaluate.paired(new_monthly, old_monthly)
    interval = (
        paired_ir(new_daily, old_daily, 252, 21)
        if old_daily is not None
        else paired_ir(new_monthly, old_monthly)
    )
    process = process_ok(old_m) and process_ok(new_m)
    by_year = {}
    chronological = True
    if old_daily is not None:
        for year in sorted(set(old_daily.index.year) & set(new_daily.index.year)):
            a, b = old_daily[old_daily.index.year == year], new_daily[new_daily.index.year == year]
            delta = float(np.sqrt(252) * (b.mean() / b.std() - a.mean() / a.std()))
            by_year[str(year)] = {"delta_ir": delta, "paired_delta_ir": paired_ir(b, a, 252, 21)}
        selection, confirmation = by_year.get("2019", {}), by_year.get("2020", {})
        ci = confirmation.get("paired_delta_ir")
        chronological = bool(
            selection.get("delta_ir", -np.inf) > 0
            and confirmation.get("delta_ir", -np.inf) >= floor
            and ci is not None
            and ci["lo90"] > 0
        )
    passed = bool(
        process
        and chronological
        and d_ir > 0
        and d_ir >= floor
        and interval is not None
        and interval["lo90"] > 0
    )
    return {
        "delta_ir": float(d_ir),
        "paired_monthly": paired,
        "paired_delta_ir": interval,
        "process_passed": process,
        "by_year": by_year,
        "select_2019_confirm_2020": chronological,
        "promoted": passed,
    }


def process_ok(result: dict) -> bool:
    return (
        result["breaches"] == 0
        and not result["reconcile"]
        and result.get("monthly_reconciliation", {"passed": True})["passed"]
        and (not result.get("policy_required") or result["policy_breach_days"] == 0)
    )


def select_candidate(runs: dict, gates: dict, ma1_wins: bool) -> tuple[str | None, str | None]:
    candidate = "E0" if process_ok(runs["E0"]) else None
    if candidate is not None:
        for nxt, key in (("E1", "E1_over_E0"), ("E2", "E2_over_E1")):
            if not gates[key]["promoted"]:
                break
            candidate = nxt
        if candidate == "E2":
            if ma1_wins:
                candidate = "E2_Ma1"
            if gates["E3_over_winner"]["promoted"]:
                candidate = "E3"
    ship = candidate
    if candidate is None or runs[candidate]["active_ann_mean"] <= 0:
        ship = "fallback" if process_ok(runs["fallback"]) else None
    return candidate, ship


# Annual cost split of a run, per N, for the hurdle formula (impact scales).
def _costs_by_n(metrics_e2: dict, n_ref: int = 300) -> dict[int, float]:
    c = metrics_e2["cost_pct_nav_yr"]
    fixed = c["spread"] + c["fees"] + c["borrow"]
    return {n: float(fixed + c["impact"] * np.sqrt(n_ref / n)) for n in (250, 300, 450)}


# Runs the ladder and writes out/engine/ladder.json.
def main(force: bool = False) -> dict:
    m = load_mandate()
    if len(steps()) > m.policy.max_configs:
        raise ValueError("monthly ladder exceeds the frozen configuration budget")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "mandate": dataclasses.asdict(m),
                "window_eom": [str(e.date()) for e in WINDOW],
                "fingerprints": {
                    name: target_fingerprint(m, step) for name, step in steps().items()
                },
                "selection_year": 2019,
                "confirmation_year": 2020,
                "registry_configs": 5,
                "registry_total": 82,
                "source_identity": SOURCE_IDENTITY,
                "scope": "Monthly E0-E3; OOS remains sealed",
            },
            indent=2,
        )
        + "\n"
    )
    world = World(m)
    plan = steps()
    runs, monthly, daily_active = {}, {}, {}

    def execute(name: str, step: optimize.Step):
        targets, logs = build_targets(world, step, force=force)
        ledger, positions = run_books(world, targets)
        runs[name] = metrics(world, ledger, positions, enforce_policy=step.bands) | {
            "build_logs": logs,
            "monthly_reconciliation": monthly_reference(ledger, positions, world.market["returns"]),
        }
        monthly[name] = monthly_active(ledger, world)
        daily_active[name] = (
            ledger["ret"].iloc[1:] - world.rf.reindex(ledger.index[1:]) - m.hard.premium / 252
        )
        ledger.to_parquet(OUT / f"ledger_{name}.parquet")
        positions.to_parquet(OUT / f"positions_{name}.parquet", index=False)
        breaches, _ = checker.check(
            positions, inputs.panel(["me", "me_company"]), m, ramp_days=5, sessions=ledger.index[1:]
        )
        breaches.to_parquet(OUT / f"breaches_{name}.parquet", index=False)
        checker.policy_diagnostics(positions, world.policy_inputs(), m).to_parquet(
            OUT / f"policy_{name}.parquet"
        )
        return targets, ledger

    def compare(old, new, floor=GATE_FLOOR):
        return gate(
            runs[old],
            runs[new],
            monthly[old],
            monthly[new],
            daily_active[old],
            daily_active[new],
            floor=floor,
        )

    execute("E0", plan["E0"])
    execute("E1", plan["E1"])
    e2_targets, _ = execute("E2", plan["E2"])
    execute("E2_Ma1", plan["E2_Ma1"])
    ma1_gate = compare("E2", "E2_Ma1", floor=0)
    # D6: Ma1 replaces MaInf only on net IR; the gate's IR floor does not
    # apply to a same-complexity column swap, so decide on delta + paired CI.
    ma1_wins = ma1_gate["promoted"]
    winner = "Elasso_Ma1" if ma1_wins else "Elasso_MaInf"
    winner_run = "E2_Ma1" if ma1_wins else "E2"
    costs = _costs_by_n(runs[winner_run], n_ref=round(runs[winner_run]["avg_names"]))
    n_pick, hurdle = optimize.hurdle_pick(FROZEN_IC, costs, gross=m.policy.target_gross)
    plan = steps(n_e3=n_pick, winner=winner)
    e3_targets, e3_ledger = execute("E3", plan["E3"])
    # IR(k) scale check and stressed-ADV sensitivity on the E3 direction.
    ir_k = {}
    scale_diagnostics = {}
    for k in (0.5, 0.75, 1.0):
        led, pos = run_books(world, e3_targets, gross_scale=k)
        scale_diagnostics[str(k)] = metrics(world, led, pos, enforce_policy=True)
        ir_k[str(k)] = scale_diagnostics[str(k)]["net_ir_daily"]
    led_s, pos_s = run_books(world, e3_targets, adv_scale=0.5)
    stressed_metrics = metrics(world, led_s, pos_s, enforce_policy=True)
    stressed = stressed_metrics["net_ir_daily"]
    led_s.to_parquet(OUT / "ledger_E3_adv_half.parquet")
    pos_s.to_parquet(OUT / "positions_E3_adv_half.parquet", index=False)
    spread_sensitivity = {}
    for multiplier in m.policy.spread_multipliers:
        led, pos = run_books(world, e3_targets, spread_scale=multiplier)
        spread_sensitivity[str(multiplier)] = metrics(world, led, pos, enforce_policy=True)
        led.to_parquet(OUT / f"ledger_E3_spread_{multiplier}.parquet")
        pos.to_parquet(OUT / f"positions_E3_spread_{multiplier}.parquet", index=False)
    fb_ledger, fb_pos = run_books(world, fallback_targets(world))
    runs["fallback"] = metrics(world, fb_ledger, fb_pos, enforce_policy=True)
    fb_ledger.to_parquet(OUT / "ledger_fallback.parquet")
    fb_pos.to_parquet(OUT / "positions_fallback.parquet", index=False)
    monthly["fallback"] = monthly_active(fb_ledger, world)
    gates = {
        "E1_over_E0": compare("E0", "E1"),
        "E2_over_E1": compare("E1", "E2"),
        "Ma1_over_MaInf_at_E2": ma1_gate | {"winner": winner},
        "E3_over_winner": compare(winner_run, "E3"),
    }
    gates["E3_over_winner"]["stress_process_passed"] = process_ok(stressed_metrics)
    gates["E3_over_winner"]["promoted"] &= process_ok(stressed_metrics)
    candidate, ship = select_candidate(runs, gates, ma1_wins)
    if _source_identity() != SOURCE_IDENTITY:
        raise RuntimeError("source changed during validation; rerun before using the report")
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["final_steps"] = {name: dataclasses.asdict(step) for name, step in plan.items()}
    manifest["final_fingerprints"] = {
        name: target_fingerprint(m, step) for name, step in plan.items()
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    report = {
        "window_eom": [str(WINDOW[0].date()), str(WINDOW[1].date())],
        "runs": {
            k: {kk: vv for kk, vv in v.items() if kk != "build_logs"} for k, v in runs.items()
        },
        "gates": gates,
        "hurdle": {"n_pick": n_pick, "table": hurdle, "ic_frozen": FROZEN_IC, "costs_by_n": costs},
        "ir_by_gross_scale": ir_k,
        "ir_stressed_adv_half": stressed,
        "stress_adv_half": stressed_metrics,
        "spread_sensitivity": spread_sensitivity,
        "scale_diagnostics": scale_diagnostics,
        "candidate_by_gates": candidate,
        "ship": ship,
        "monthly_candidate_eligible": ship is not None,
        "ready_for_freeze": False,
        "ready_for_oos": False,
        "scope": (
            "Monthly E0-E3 validation only; E4 daily repairs, full reporting "
            "and final freeze remain separate"
        ),
        "risk_calibration_caveat": json.loads((OUT.parent / "risk/report.json").read_text())[
            "half_lives"
        ]["84"],
        "registry_note": "E0,E1,E2,Ma1-trial,E3 = 5 configs; running total 82",
        "validation_reuse": (
            "2017-2020 was repeatedly used for model selection and debugging; "
            "the 2019/2020 split is diagnostic, not a fresh holdout."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ladder.json").write_text(json.dumps(report, indent=2, default=run._plain) + "\n")
    pd.DataFrame(monthly).to_parquet(OUT / "monthly_active.parquet")
    return report


if __name__ == "__main__":
    import sys

    r = main(force="--force" in sys.argv)
    for name, v in r["runs"].items():
        print(
            f"{name:9s} netIR {v['net_ir_daily']:+.3f} grossIR {v['gross_ir_daily']:+.3f} "
            f"active {v['active_ann_mean'] * 100:+.2f}% vol {v['active_ann_vol'] * 100:.2f}% "
            f"turn {v['turnover_annualised']:.2f} breaches {v['breaches']} "
            f"beta {v['beta_sp500_daily']['beta']:+.3f} (t {v['beta_sp500_daily']['beta_t']:+.2f})"
        )
    print("gates:", {k: (round(v["delta_ir"], 3), v["promoted"]) for k, v in r["gates"].items()})
    print(
        "hurdle N:",
        r["hurdle"]["n_pick"],
        "| IR(k):",
        r["ir_by_gross_scale"],
        "| stressed ADV IR:",
        r["ir_stressed_adv_half"],
    )
    print("candidate:", r["candidate_by_gates"], "-> ship:", r["ship"])
