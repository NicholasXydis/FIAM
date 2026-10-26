# The controller: two-stage support + one QP per formation (R§5).
#
# v1 objective (all horizons H = sessions to next review):
#   min (gamma/2) w'Sigma_H w - mu'w + s'|q| + c'q^2
#       + (H/252) b'max(-w,0) + u'w^2 + ordered slack penalties,
#   q = w - w_pre; E5 adds lambda_b (beta'w)^2 inside the hard beta band,
#   direction-aware jump variance in w'Sigma w (shorts p_up*J_up^2, longs
#   p_dn*J_dn^2, a month's jump per H/21) and caps gross instead of fixing it,
#   so the book is: max return - costs, min vol, min beta, subject to the
#   rules (user, 2026-10-26); the impact term is a quadratic proxy matched at the average
#   target position to Y*sigma_i*sqrt(NAV/(5*ADV_i))*|q|^(3/2), the fill law.
# Signs are fixed before the solve (hedge_sleeve_max = 0 in config), so
# gross is linear and exact (side'w = target gross). HARD rules never take
# slack; policy bands (net, sector, beta, size, wide styles) yield through
# slacks whose sizes are logged - the log is the pre-trade explanation.
# Scale is the frozen target gross (largest the HARD rules allow minus a
# drift buffer); IR(k) rescaling is reporting, in ladder.py.

import dataclasses
import math
from dataclasses import dataclass, field
from statistics import NormalDist

import cvxpy as cp
import numpy as np
import pandas as pd

from fiam.v4b.engine import fees
from fiam.v4b.engine.mandate import Final
from fiam.v4b.risk import covariance

# Exact-penalty weights on policy slacks (return units): tier 1 >> tier 2 >> alpha.
M1, M2 = 5.0, 1.0
# Sessions over which the simulator may spill one rebalance (sim Setup).
EXEC_DAYS = 5
# Fees: the dated IBKR/SEC/FINRA schedule in engine/fees.py, the same lines the
# execution backend charges (convex per-dollar form here).
# Reference TE for expressing style bands in vol units [Judgement].
SIGMA_REF = 0.04
# Vol guardrail (annualised); neutral books sit far inside it (R§5).
SIGMA_MAX = 0.15


# One ladder step's construction choices (see ladder.STEPS).
@dataclass(frozen=True)
class Step:
    name: str
    column: str = "Elasso_MaInf"
    support: str = "greedy"  # "rank" (E0) or "greedy" (stage 0/1/2)
    bands: bool = True  # sector/beta/size + wide alpha-style bands
    borrow_term: bool = True
    trade_costs: bool = False  # s'|q| + c'q^2 inside the objective (E3)
    uncertainty: bool = False  # diagonal u'w^2 (E2)
    incumbent_credit: bool = False  # hysteresis in support scores (E3)
    jump_risk: bool = False  # opposite-direction jump caps and budgets (E4, D12)
    jump_var: bool = False  # direction-aware jump variance in the risk term (E5)
    beta_penalty: bool = False  # lambda_b (beta'w)^2 in the objective (E5)
    gross_cap: bool = False  # side'w <= target gross instead of == (E5)
    vol_target: bool = False  # predicted vol <= policy.vol_target, small risk price (E5)
    names: int = 300
    # E6 two-step (D18): support="twostep" selects by the HHRZ decile sort
    # ("vw" | "ew"), then the QP minimises risk at mu'w >= floor_rho x mu'w_ref.
    weighting: str = "vw"
    floor_rho: float = 0.9
    vol_cap: float = 0.12


# Everything one formation's solve reads (all knowable at the eom close).
@dataclass
class Formation:
    eom: pd.Timestamp
    mu: pd.Series  # centred, calibrated, horizon-converted expected returns
    snap: dict  # risk snapshot (B, F, F1, d, beta, sxx, month)
    adv: pd.Series  # lagged daily dollar volume, $
    half_spread: pd.Series
    borrow: pd.Series  # annual borrow rate by name
    coverage: pd.Series  # share of the 147 present at eom
    w_pre: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    nav: float = 1e9
    horizon: int = 21
    # The fill model's lagged 63-session vol, so optimizer impact and native
    # fills read the same sigma. Empty in synthetic tests -> risk-model vol.
    sigma: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    # Raw close at the signal day, for per-share fees. Empty -> $10 a share.
    price: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    # Out-of-sample next-month jump probabilities (risk/jumps.py): up for
    # shorts, down for longs. Empty -> no jump terms.
    p_up: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    p_dn: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    # me ($m) of every NYSE name in the panel at eom, for the HHRZ breakpoints
    # (E6). Empty -> every name counts as NYSE.
    nyse_me: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


# Per-name position cap: policy cap, liquidity cap, hard cap (R§2, R§5).
def position_caps(f: Formation, m: Final) -> pd.Series:
    p = m.policy
    liq = p.participation * f.adv * p.days_to_exit_max / f.nav
    return liq.clip(upper=p.position_cap).clip(upper=m.hard.name_cap)


# Short-side cap multiplier from the up-jump probability (D12): a name with
# k times the pool's mean p_up may hold 1/k of the cap, so its jump loss
# stays at the pool-average name's. Names without a probability keep 1.
def short_jump_scale(f: Formation, step: Step) -> pd.Series:
    if not step.jump_risk or f.p_up.dropna().empty:
        return pd.Series(1.0, index=f.snap["B"].index)
    p = f.p_up.reindex(f.snap["B"].index)
    ratio = (f.p_up.dropna().mean() / p).clip(upper=1.0)
    return ratio.fillna(1.0)


# Total daily vol per name from the snapshot: sqrt((B F1 B')_ii + d_i).
def total_vol(f: Formation) -> pd.Series:
    B = f.snap["B"]
    F1 = f.snap["F1"].reindex(index=B.columns, columns=B.columns).to_numpy(dtype=float)
    diag = np.einsum("ij,jk,ik->i", B.to_numpy(dtype=float), F1, B.to_numpy(dtype=float))
    return pd.Series(np.sqrt(np.maximum(diag, 0) + f.snap["d"].to_numpy()), index=B.index)


# Return cost of trading weight q over EXEC_DAYS at participation. This is the
# simulator's square-root law in return units:
#   Y * sigma * sqrt(NAV / (D * ADV)) * q^(3/2).
# The simulator trades q/D each day, so the D-day total is not the one-day
# q^(3/2) law with the full order. Keeping the two in one function prevents the
# optimizer and the fill engine from drifting apart.
def impact_cost(q, sigma, adv, nav, impact_y, exec_days: int = EXEC_DAYS):
    q = np.abs(np.asarray(q, dtype=float))
    sigma = np.asarray(sigma, dtype=float)
    adv = np.maximum(np.asarray(adv, dtype=float), 1.0)
    return impact_y * sigma * np.sqrt(float(nav) / (exec_days * adv)) * q**1.5


# A quadratic proxy c*q^2 matched to impact_cost at the average target
# position. It is exact at q_ref, conservative for larger trades and mildly
# optimistic for smaller ones; that direction is deliberate, because the usual
# failure is an optimizer that believes trading is cheaper than the fill model.
def impact_quadratic_coef(sigma, adv, nav, impact_y, q_ref) -> np.ndarray:
    sigma = np.asarray(sigma, dtype=float)
    adv = np.maximum(np.asarray(adv, dtype=float), 1.0)
    q_ref = np.maximum(np.asarray(q_ref, dtype=float), 1e-9)
    return impact_y * sigma * np.sqrt(float(nav) / (EXEC_DAYS * adv)) / np.sqrt(q_ref)


# Previous target drifted by realised returns into this formation (w-).
# Missing returns count as flat; cash/cost drift is the simulator's truth.
def drift(w_prev: pd.Series, returns_block: pd.DataFrame) -> pd.Series:
    if w_prev.empty:
        return w_prev
    cols = w_prev.index.intersection(returns_block.columns)
    growth = (1 + returns_block[cols].fillna(0.0)).prod() - 1
    h = w_prev.copy()
    h.loc[cols] = w_prev.loc[cols] * (1 + growth.to_numpy())
    nav_growth = float((h - w_prev.reindex(h.index).fillna(0.0)).sum())
    return h / (1 + nav_growth)


# Style band half-widths in vol units: share * sigma_ref / sigma_F,k (annual).
def _band_widths(f: Formation, share: float) -> pd.Series:
    F1 = f.snap["F1"]
    ann = np.sqrt(np.diag(F1.to_numpy(dtype=float)) * 252)
    return share * SIGMA_REF / pd.Series(ann, index=F1.index).replace(0, np.nan)


# The QP. With signs=None it is the stage-0 free-sign solve (no min size,
# the step's exposure bands); with signs it is stage 2 on the chosen support. Returns
# (weights, log) or (None, log) - never a fabricated book.
# With floor (E6 step 2) the return leaves the objective and becomes the hard
# constraint mu'w >= floor: the solve minimises risk, beta and costs only.
def solve_qp(
    f: Formation, m: Final, step: Step, names: pd.Index, signs: pd.Series | None,
    floor: float | None = None,
) -> tuple[pd.Series | None, dict]:
    p, B = m.policy, f.snap["B"]
    names = pd.Index([n for n in names if n in B.index and n in f.mu.index])
    if signs is not None:  # a signed name must be able to hold the minimum size
        caps_all = position_caps(f, m).reindex(names).fillna(0.0)
        names = names[caps_all.to_numpy() >= p.position_min]
    log = {"eom": str(f.eom.date()), "step": step.name, "names_in": int(len(names))}
    if len(names) < m.hard.names_min:
        return None, log | {"status": "support below names_min"}
    mu = f.mu.reindex(names).fillna(0.0).to_numpy(dtype=float)
    wpre = f.w_pre.reindex(names).fillna(0.0).to_numpy(dtype=float)
    Bm = B.loc[names].to_numpy(dtype=float)
    F = f.snap["F"].reindex(index=B.columns, columns=B.columns).to_numpy(dtype=float)
    F = 0.5 * (F + F.T)
    d = f.snap["d"].reindex(names).to_numpy(dtype=float)
    caps = position_caps(f, m).reindex(names).fillna(0.0).to_numpy(dtype=float)
    short_caps = caps * short_jump_scale(f, step).reindex(names).fillna(1.0).to_numpy()
    adv = f.adv.reindex(names).fillna(0.0).to_numpy(dtype=float)
    order_cap = p.participation * adv * EXEC_DAYS / f.nav + np.abs(wpre)
    n = len(names)
    w = cp.Variable(n)
    q = w - wpre
    bw = Bm.T @ w
    risk = cp.quad_form(bw, cp.psd_wrap(F)) + f.horizon * cp.sum(cp.multiply(d, cp.square(w)))
    if step.jump_var and signs is not None and not f.p_up.dropna().empty:
        side_j = signs.reindex(names).fillna(1.0).to_numpy(dtype=float)
        pu = f.p_up.reindex(names).fillna(float(f.p_up.dropna().mean())).to_numpy(dtype=float)
        pd_ = f.p_dn.reindex(names).fillna(float(f.p_dn.dropna().mean())).to_numpy(dtype=float)
        jv = np.where(side_j < 0, pu * p.jump_up_size**2, pd_ * p.jump_dn_size**2) * f.horizon / 21
        risk = risk + cp.sum(cp.multiply(jv, cp.square(w)))
    # Stage 0 only finds support and signs; it keeps the E3 risk price and
    # guardrail so a vol-target step does not concentrate its support.
    stage2_target = step.vol_target and signs is not None
    gamma = p.vol_target_risk_aversion if stage2_target else p.risk_aversion
    obj = 0.5 * gamma * risk - (mu @ w if floor is None else 0.0)
    beta_vec = f.snap["beta"].reindex(names).fillna(1.0).to_numpy(dtype=float)
    if step.beta_penalty and signs is not None:
        obj = obj + p.beta_penalty * cp.square(beta_vec @ w)
    cons = [cp.abs(q) <= np.maximum(order_cap, 1e-9)]
    if floor is not None:
        cons += [mu @ w >= floor]
    slacks, shadow_constraints = {}, {}
    if signs is None:  # stage 0: free sign, gross ceiling, no minimum size
        month = f.snap["month"].loc[names]
        cons += [
            w >= -short_caps * month["short_ok"].to_numpy(dtype=float),
            w <= caps * month["long_ok"].to_numpy(dtype=float),
            cp.norm1(w) <= p.target_gross,
        ]
        sn = cp.Variable(nonneg=True)
        cons += [cp.sum(w) <= sn, -cp.sum(w) <= sn]
        obj = obj + M1 * sn
        slacks["net"] = sn
    else:
        side = signs.reindex(names).fillna(1.0).to_numpy(dtype=float)
        lo = np.where(side > 0, p.position_min, -short_caps)
        hi = np.where(side > 0, caps, -p.position_min)
        # Gross equality at the frozen target (R§5 scale doctrine). When
        # capacity cannot fund it neutrally, build_book lowers the target
        # explicitly instead of letting slacks buy gross invisibly.
        cons += [w >= lo, w <= hi, (side @ w <= p.target_gross) if step.gross_cap else (side @ w == p.target_gross)]
        sn = cp.Variable(nonneg=True)
        cons += [cp.sum(w) <= sn, -cp.sum(w) <= sn]
        # The net band is a HARD mandate limit, not a policy band. Keep the
        # soft target for the objective, but never let the solver cross the
        # reported hard rule even if the penalty is finite.
        cons += [cp.sum(w) <= m.hard.net_band, -cp.sum(w) <= m.hard.net_band]
        obj = obj + M1 * sn
        slacks["net"] = sn
        if step.jump_risk and not f.p_up.dropna().empty:
            # Book jump budgets (D12), linear because signs are fixed: the
            # short book's weighted p_up stays within jump_short_ratio of the
            # pool mean; the long book's p_dn within jump_long_ratio.
            for key, prob, sgn, ratio in (
                ("jump_short", f.p_up, -1.0, p.jump_short_ratio),
                ("jump_long", f.p_dn, 1.0, p.jump_long_ratio),
            ):
                pool = float(prob.dropna().mean())
                excess = prob.reindex(names).fillna(pool).to_numpy(dtype=float) - ratio * pool
                mask = (side == sgn).astype(float)
                sj = cp.Variable(nonneg=True)
                cons += [(sgn * mask * excess) @ w <= sj]
                obj = obj + M1 * sj
                slacks[key] = sj
        if step.borrow_term:
            b = f.borrow.reindex(names).fillna(p.borrow_flat_other).to_numpy(dtype=float)
            coef = np.where(side < 0, -b, 0.0)  # shorts have w<0: cost = -b*w > 0
            obj = obj + (f.horizon / 252) * (coef @ w)
    if step.trade_costs:
        s = f.half_spread.reindex(names).fillna(0.005).to_numpy(dtype=float)
        sig = (
            f.sigma.reindex(names) if not f.sigma.empty else total_vol(f).reindex(names)
        )
        sig = sig.fillna(0.02).to_numpy(dtype=float)
        q_ref = np.maximum(p.target_gross / max(n, 1), p.position_min)
        c = impact_quadratic_coef(sig, adv, f.nav, p.impact_y, q_ref)
        obj = obj + s @ cp.abs(q) + cp.sum(cp.multiply(c, cp.square(q)))
        # Per-share commission and CAT both sides; SEC and TAF only on sales.
        px = f.price.reindex(names).to_numpy(dtype=float) if not f.price.empty else np.full(n, np.nan)
        obj = obj + fees.per_dollar(px) @ cp.abs(q) + fees.per_dollar_sold(px) @ cp.pos(-q)
    if step.uncertainty:
        cov = f.coverage.reindex(names).fillna(0.5).clip(lower=0.1).to_numpy(dtype=float)
        u = p.uncertainty_scale * f.horizon * d / cov
        obj = obj + cp.sum(cp.multiply(u, cp.square(w)))
    if step.bands:
        month = f.snap["month"].loc[names]
        sectors = pd.get_dummies(month["sector"]).reindex(
            columns=sorted(month["sector"].dropna().unique()), fill_value=0.0
        )
        ssec = cp.Variable(len(sectors.columns), nonneg=True)
        sec_exp = sectors.to_numpy(dtype=float).T @ w
        sec_cons = [sec_exp <= p.sector_band + ssec, -sec_exp <= p.sector_band + ssec]
        cons += sec_cons
        shadow_constraints["sector"] = (list(sectors.columns), sec_cons)
        sbeta = cp.Variable(nonneg=True)
        beta = f.snap["beta"].reindex(names).to_numpy(dtype=float)
        beta_cons = [beta @ w <= p.beta_band + sbeta, -beta @ w <= p.beta_band + sbeta]
        cons += beta_cons
        shadow_constraints["beta"] = (["mkt"], beta_cons)
        widths = _band_widths(f, 0.25)
        wide = _band_widths(f, 1.0)
        tier2 = []
        for k, col in enumerate(B.columns):
            if col == "size":
                s_k = cp.Variable(nonneg=True)
                band_cons = [bw[k] <= widths[col] + s_k, -bw[k] <= widths[col] + s_k]
                cons += band_cons
                shadow_constraints[col] = ([col], band_cons)
                tier2.append(s_k)
                slacks["size"] = s_k
            elif col in ("value", "momentum", "profitability", "investment"):
                s_k = cp.Variable(nonneg=True)
                band_cons = [bw[k] <= wide[col] + s_k, -bw[k] <= wide[col] + s_k]
                cons += band_cons
                shadow_constraints[col] = ([col], band_cons)
                tier2.append(s_k)
        obj = obj + M1 * (cp.sum(ssec) + sbeta) + M2 * sum(tier2)
        slacks |= {"sector_max": ssec, "beta": sbeta}
    # Annualised vol guardrails (base and stressed), hard but generous.
    var_cap = (p.vol_target if stage2_target else SIGMA_MAX) ** 2 * f.horizon / 252
    cons += [risk <= var_cap]
    F_stressed = (
        covariance.stressed(f.snap["F"])
        .reindex(index=B.columns, columns=B.columns)
        .to_numpy(dtype=float)
    )
    risk_s = cp.quad_form(bw, cp.psd_wrap(0.5 * (F_stressed + F_stressed.T))) + f.horizon * cp.sum(
        cp.multiply(d, cp.square(w))
    )
    cons += [risk_s <= var_cap * 4]  # stressed vols run ~2x; guardrail only
    problem = cp.Problem(cp.Minimize(obj), cons)
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.SolverError as exc:
        return None, log | {"status": f"solver error: {exc}"}
    if w.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
        return None, log | {"status": str(problem.status)}
    out = pd.Series(np.asarray(w.value).ravel(), index=names)
    got = {
        k: float(v.value) if np.ndim(v.value) == 0 else float(np.max(v.value))
        for k, v in slacks.items()
        if v.value is not None
    }
    shadows = {}
    for key, (columns, pair) in shadow_constraints.items():
        value = np.atleast_1d(pair[0].dual_value) - np.atleast_1d(pair[1].dual_value)
        shadows[key] = dict(zip(columns, value.astype(float)))
    return out, log | {"status": problem.status, "slacks": got, "shadows": shadows,
                       "objective": float(problem.value)}


# Eligible candidates per side: longs need long_ok, shorts need short_ok
# (the $500m floor at formation, D3), both need a usable position cap.
def _candidates(f: Formation, m: Final, step: Step = Step("any")) -> pd.DataFrame:
    month = f.snap["month"].copy()
    month["mu"] = f.mu.reindex(month.index)
    month["cap"] = position_caps(f, m).reindex(month.index)
    month["cap_short"] = month["cap"] * short_jump_scale(f, step).reindex(month.index).fillna(1.0)
    month = month[month["mu"].notna() & (month["cap"] >= m.policy.position_min)]
    # A short-only name whose jump-scaled cap is below the minimum cannot short.
    month.loc[month["cap_short"] < m.policy.position_min, "short_ok"] = False
    return month


# E0 support: extreme forecasts only, half the names per side by rank.
def rank_support(f: Formation, m: Final, step: Step) -> tuple[pd.Index, pd.Series]:
    c = _candidates(f, m)
    longs = c[c["long_ok"]].sort_values("mu", ascending=False).head(step.names // 2)
    shorts = c[c["short_ok"]].sort_values("mu").head(step.names - len(longs))
    names = longs.index.union(shorts.index)
    signs = pd.Series(-1.0, index=names)
    signs.loc[longs.index] = 1.0
    return names, signs


# Stage 0 signs from a free-sign solve on the enlarged support.
def _stage0_signs(f: Formation, m: Final, step: Step, c: pd.DataFrame):
    # All liquid candidates provide both sides of each sector. Global alpha
    # tails alone can omit the hedge names in a high-forecast sector.
    enlarged = c.index
    # Stage 0 must see the final exposure limits before it fixes signs.
    # Sector-level alpha otherwise puts entire sectors on one side and no
    # subsequent support swap or gross reduction can recover neutrality.
    w0, log = solve_qp(f, m, dataclasses.replace(step, name=step.name + "_stage0"), enlarged, None)
    signs = pd.Series(np.where(c["mu"] >= 0, 1.0, -1.0), index=c.index)
    if w0 is not None:
        live = w0[w0.abs() > 1e-6]
        signs.loc[live.index.intersection(signs.index)] = np.sign(
            live.reindex(signs.index).dropna()
        )
    # Shorts must be short-eligible whatever stage 0 preferred.
    signs.loc[~c["short_ok"].fillna(False).to_numpy()] = 1.0
    shadow = pd.Series(0.0, index=c.index)
    for key, values in log.get("shadows", {}).items():
        if key == "sector":
            shadow += c["sector"].map(values).fillna(0.0)
        else:
            for col, value in values.items():
                shadow += f.snap["B"][col].reindex(c.index) * value
    return signs, shadow


# Stage 1: greedy per side by (mu - borrow - entry cost)/sigma_e.
# Each side fills half the book under the same sector quotas (1.5x the
# pooled proportional share), then sector repair drops majority-side names
# until every sector's achievable net interval meets the sector band, then
# cap repair tops up any side short of half the target gross. Selection is
# per side because pooled scores fill the book with longs and strand the
# short leg (observed Dec 2019: 239 longs vs 100 shorts, sector slack 0.16).
def greedy_support(f: Formation, m: Final, step: Step) -> tuple[pd.Index, pd.Series, dict]:
    p = m.policy
    c = _candidates(f, m, step)
    signs, shadow = _stage0_signs(f, m, step, c)
    c["side"] = signs
    c = c[((c["side"] > 0) & c["long_ok"]) | ((c["side"] < 0) & c["short_ok"])].copy()
    c["cap"] = np.where(c["side"] < 0, c["cap_short"], c["cap"])
    sig_e = np.sqrt(np.maximum(f.snap["d"].reindex(c.index).to_numpy(), 1e-12) * f.horizon)
    borrow = f.borrow.reindex(c.index).fillna(p.borrow_flat_other).to_numpy()
    borrow_cost = np.where(c["side"] < 0, borrow * f.horizon / 252, 0.0)
    spread = f.half_spread.reindex(c.index).fillna(0.005).to_numpy()
    entry = np.zeros(len(c))
    exit_credit = np.zeros(len(c))
    if step.trade_costs:
        # mu is return per dollar held, so the support score needs the actual
        # square-root impact at the reference position, not
        # (NAV/ADV) * reference_size (which is ~100x too large at 250 names).
        sig = (
            f.sigma.reindex(c.index) if not f.sigma.empty else total_vol(f).reindex(c.index)
        )
        sig = sig.fillna(0.02).to_numpy()
        adv = np.maximum(f.adv.reindex(c.index).fillna(0.0).to_numpy(), 1.0)
        reference_size = np.minimum(
            p.target_gross / max(step.names, 1), c["cap"].to_numpy()
        )
        px = f.price.reindex(c.index).to_numpy(dtype=float) if not f.price.empty else np.nan
        entry = spread + fees.per_dollar(px) + impact_cost(
            reference_size, sig, adv, f.nav, p.impact_y
        )
        prior = f.w_pre.reindex(c.index).fillna(0.0).to_numpy()
        held = (prior * c["side"].to_numpy()) > 1e-9
        # Keeping the same side avoids entry and saves a genuine exit cost.
        # This is holdings dependence, not a forecast bonus for held names.
        entry = np.where(held, 0.0, entry)
        if step.incumbent_credit:
            exit_credit = np.where(
                held,
                spread + fees.per_dollar(px) + impact_cost(np.abs(prior), sig, adv, f.nav, p.impact_y),
                0.0,
            )
    reduced_mu = c["mu"] - shadow.reindex(c.index)
    score = (
        c["side"].to_numpy() * reduced_mu.to_numpy() - borrow_cost - entry + exit_credit
    ) / sig_e
    if step.incumbent_credit and not step.trade_costs and not f.w_pre.empty:
        held = c.index.isin(wpre_live(f.w_pre))
        score = score + np.where(held, spread / sig_e, 0.0)
    c["score"] = score
    half_n = step.names // 2
    shares = c["sector"].value_counts(normalize=True)
    quota = (1.5 * half_n * shares).clip(lower=5).to_dict()
    need = p.target_gross / 2
    chosen: list = []
    for side_val in (1.0, -1.0):
        pool = c[c["side"] == side_val].sort_values("score", ascending=False)
        counts: dict = {}
        picked = 0
        for permno, row in pool.iterrows():
            if picked >= half_n:
                break
            if counts.get(row["sector"], 0) >= quota.get(row["sector"], 5):
                continue
            chosen.append(permno)
            counts[row["sector"]] = counts.get(row["sector"], 0) + 1
            picked += 1
    chosen = _sector_repair(c, chosen, p)
    if step.bands:
        chosen = _exposure_repair(f, c, chosen, p)
        chosen = _sector_repair(c, chosen, p)
    # Cap repair: top up a side whose caps cannot fund half the target gross.
    chosen_set = set(chosen)
    for side_val in (1.0, -1.0):
        have = float(c.loc[c.index.isin(chosen_set) & (c["side"] == side_val), "cap"].sum())
        if have >= need:
            continue
        rest = c[(c["side"] == side_val) & ~c.index.isin(chosen_set)].sort_values(
            "score", ascending=False
        )
        for permno, row in rest.iterrows():
            if len(chosen_set) >= m.hard.names_max:
                break
            chosen.append(permno)
            chosen_set.add(permno)
            have += float(row["cap"])
            if have >= need:
                break
    names = pd.Index(sorted(chosen_set))
    sel = c.loc[names]
    caps = sel.groupby("side")["cap"].sum().to_dict()
    return (
        names,
        signs.reindex(names),
        {
            "cap_long": float(caps.get(1.0, 0.0)),
            "cap_short": float(caps.get(-1.0, 0.0)),
            "n_long": int((sel["side"] > 0).sum()),
            "n_short": int((sel["side"] < 0).sum()),
        },
    )


# Exact min/max of sum(a_i x_i) with mins <= x <= caps and sum(x) = total.
def _side_extremes(a: np.ndarray, caps: np.ndarray, mins: np.ndarray, total: float):
    def fill(order):
        x = mins.copy()
        left = total - x.sum()
        for i in order:
            add = min(caps[i] - x[i], max(left, 0.0))
            x[i] += add
            left -= add
        return float(a @ x)

    ascending = np.argsort(a)
    return fill(ascending), fill(ascending[::-1])


# Achievable interval for a linear exposure under net 0 at gross G:
# longs sum to G/2 at +a, shorts to G/2 at -a (weights signed).
def _exposure_interval(sel: pd.DataFrame, a: pd.Series, p) -> tuple[float, float]:
    total = p.target_gross / 2
    parts = []
    for side_val in (1.0, -1.0):
        part = sel[sel["side"] == side_val]
        vals = side_val * a.reindex(part.index).fillna(0.0).to_numpy(dtype=float)
        caps = part["cap"].to_numpy(dtype=float)
        mins = np.full(len(part), p.position_min)
        if caps.sum() < total or mins.sum() > total:
            return (np.inf, -np.inf)  # side itself cannot fund its half
        parts.append(_side_extremes(vals, caps, mins, total))
    return parts[0][0] + parts[1][0], parts[0][1] + parts[1][1]


# Swaps support names until beta and size bands are reachable. Each swap
# drops the chosen name contributing most to the excess (worst score breaks
# ties) and adds the best-scoring unchosen name on the same side that most
# reduces it. Bounded; remaining infeasibility is left to logged slacks.
def _exposure_repair(f: Formation, c: pd.DataFrame, chosen: list, p, passes: int = 60) -> list:
    widths = _band_widths(f, 0.25)
    targets = [
        (f.snap["beta"], p.beta_band + SLACK_TOL["beta"]),
        (f.snap["B"]["size"], float(widths.get("size", 0.2)) + SLACK_TOL["size"]),
    ]
    chosen = list(chosen)
    for a, band in targets:
        for _ in range(passes):
            sel = c.loc[chosen]
            lo, hi = _exposure_interval(sel, a, p)
            if lo <= band and hi >= -band:
                break
            too_high = lo > band  # even the minimum exposure exceeds +band
            contrib = sel["side"].to_numpy() * a.reindex(sel.index).fillna(0.0).to_numpy()
            contrib_s = pd.Series(contrib, index=sel.index)
            drop_pool = contrib_s[contrib_s > 0] if too_high else contrib_s[contrib_s < 0]
            if drop_pool.empty:
                break
            drop = sel.loc[drop_pool.index].sort_values("score").index[0]
            side_val = float(sel.at[drop, "side"])
            rest = c[(c["side"] == side_val) & ~c.index.isin(chosen)].copy()
            if rest.empty:
                break
            rest_contrib = side_val * a.reindex(rest.index).fillna(0.0)
            rest = rest.assign(_c=rest_contrib.to_numpy())
            rest = rest[rest["_c"] < 0] if too_high else rest[rest["_c"] > 0]
            if rest.empty:
                chosen.remove(drop)
                continue
            add = rest.sort_values("score", ascending=False).index[0]
            chosen.remove(drop)
            chosen.append(add)
    return chosen


# Drops worst-score majority-side names sector by sector until the sector's
# achievable net interval [long_min-short_cap, long_cap-short_min] overlaps
# the sector band. Sign-fixed books cannot hedge a one-signed sector; they
# must hold less of it (eval 03 F6).
def _sector_repair(c: pd.DataFrame, chosen: list, p) -> list:
    chosen = list(chosen)
    for sector in c.loc[chosen, "sector"].unique():
        while True:
            sel = c.loc[[x for x in chosen if c.at[x, "sector"] == sector]]
            longs, shorts = sel[sel["side"] > 0], sel[sel["side"] < 0]
            lo = len(longs) * p.position_min - float(shorts["cap"].sum())
            hi = float(longs["cap"].sum()) - len(shorts) * p.position_min
            if lo <= p.sector_band and hi >= -p.sector_band:
                break
            drop_from = shorts if hi < -p.sector_band else longs
            if drop_from.empty:
                break
            chosen.remove(drop_from.sort_values("score").index[0])
    return chosen


# Names actually held before the trade (for incumbent credit).
def wpre_live(w_pre: pd.Series) -> pd.Index:
    return w_pre.index[w_pre.abs() > 1e-9]


# Slack beyond this is a failed formation at that gross, not a policy yield.
SLACK_TOL = {
    "net": 1e-6, "sector_max": 1e-6, "beta": 1e-6, "size": 1e-6,
    "jump_short": 1e-6, "jump_long": 1e-6,
}
# New entries beyond the union room are dropped (smallest |w| first) and the
# book re-solved on held names plus the entries that fit; held names keep
# their place, so names turn over at most union_room - |held| a month.
def fit_union(f: Formation, m: Final, step: Step, names, signs, w: pd.Series, held: set, union_room: int):
    new = [n for n in w.abs().sort_values(ascending=False).index if n not in held]
    allowed = max(union_room - len(held), 0)
    if len(new) <= allowed:
        return None
    keep = pd.Index([n for n in names if n in held or n in set(new[:allowed])])
    s = signs.reindex(keep) if signs is not None else None
    w2, log = solve_qp(f, m, step, keep, s)
    if w2 is not None:
        w2 = w2[w2.abs() >= 0.25 * m.policy.position_min]
    return w2, log | {"entries_trimmed": len(new) - allowed}


# Names left free under names_max for the execution overlap: exits and
# entries trade over the same days, so the union of the drifted book and the
# target must fit (the 2021+ diagnostic held 553 names on 500-name targets;
# 2017-2020 E5 held ~630 on rebalance days at 10, user 2026-10-26: cap ~440).
NAMES_HEADROOM = 60
# The union of held and target names may use the cap less a 10-name buffer:
# exits and entries trade over the same days (2017-2020 E5 with walk-forward:
# 440-name targets, 150-200 new names a month, 538-651 held on 156 days).
UNION_HEADROOM = 10
GROSS_LADDER = (1.5, 1.2, 1.0, 0.8, 0.6, 0.4)


# True when every reported policy slack is within its tolerance.
def _slacks_ok(log: dict) -> bool:
    got = log.get("slacks") or {}
    return all(got.get(k, 0.0) <= tol for k, tol in SLACK_TOL.items())


# One formation's target book with the solver ladder (R§5 F7): at each gross
# (target first, then down the ladder) accept the first solve whose policy
# slacks stay within tolerance; minimum size yields before gross does
# within a rung. The accepted rung is logged - smaller honest books in
# scarce months instead of full-gross books bought with hidden slack.
# Support grows by 50, 100, then to names_max - NAMES_HEADROOM, and a
# book is accepted first only if its union with the held names fits too; at
# the same gross a second pass drops that preference before gross gives.
def build_book(f: Formation, m: Final, step: Step) -> tuple[pd.Series | None, dict]:
    if step.support == "twostep":
        return two_step_book(f, m, step)
    attempts, supports, solved = [], {}, {}
    room = m.hard.names_max - NAMES_HEADROOM
    union_room = m.hard.names_max - UNION_HEADROOM
    held = set(wpre_live(f.w_pre))
    # The support never forces more than 10% of the eligible held names out
    # in one month: resetting a 350-name book to 250 sold ~100 incumbents
    # whatever their cost (2017-2020 E3: 0.47 of 0.63 one-way turnover was
    # entries and exits). Shrinking happens through the scores, 10% a month.
    incumbents = len(held & set(f.mu.dropna().index))
    base = min(max(step.names, math.ceil(0.9 * incumbents)), room)
    counts = (
        (step.names,)
        if step.support == "rank"
        else tuple(dict.fromkeys(min(base + k, room) for k in (0, 50, 100, room)))
    )
    extra, best = {}, []
    for gross in (m.policy.target_gross, *GROSS_LADDER):
        if gross > m.policy.target_gross:
            continue
        for strict in (True, False):
            # Support expands before gross gives; never lower leverage merely
            # because the first greedy selection could not span the bands.
            for count in counts:
                for min_size in (m.policy.position_min, 0.5 * m.policy.position_min):
                    trial = dataclasses.replace(
                        m,
                        policy=dataclasses.replace(
                            m.policy, target_gross=float(gross), position_min=float(min_size)
                        ),
                    )
                    # Support is not gross-invariant: its quota, sector repair,
                    # reference trade and stage-0 gross ceiling all read the trial
                    # policy. Caching by count alone silently built 1.8x support
                    # for a 1.0x book.
                    key = (count, float(gross), float(min_size))
                    if key not in solved:
                        support_step = dataclasses.replace(step, names=count)
                        if step.support == "rank":
                            names, signs = rank_support(f, trial, support_step)
                            extra = {}
                        else:
                            names, signs, extra = greedy_support(f, trial, support_step)
                        supports[key] = extra
                        w, log = solve_qp(f, trial, step, names, signs)
                        if w is not None:
                            w = w[w.abs() >= 0.25 * m.policy.position_min]
                        if w is not None and step.gross_cap and len(held | set(w.index)) > union_room:
                            trimmed = fit_union(f, trial, step, names, signs, w, held, union_room)
                            if trimmed is not None and trimmed[0] is not None:
                                w, log = trimmed
                        live = int((w.abs() >= 0.5 * m.policy.position_min).sum()) if w is not None else 0
                        union = len(held | set(w.index)) if w is not None else 0
                        solved[key] = w, log, live, union
                        attempts.append(
                            {
                                "support_requested": count,
                                "gross": float(gross),
                                "min_size": float(min_size),
                                "status": log.get("status"),
                                "slacks": log.get("slacks"),
                                "live_names": live,
                                "union_names": union,
                            }
                        )
                    w, log, live, union = solved[key]
                    ok = (
                        w is not None
                        and _slacks_ok(log)
                        and m.hard.names_min <= live <= m.hard.names_max
                        and (union <= (union_room if step.gross_cap else room) or not strict)
                    )
                    if ok and step.gross_cap:
                        # Gross is a ceiling: a feasible book is a candidate,
                        # and the best objective over support sizes wins.
                        best.append((log["objective"], key, w, log, live, union, strict))
                        continue
                    if ok:
                        rung = {
                            "ladder_gross": float(gross),
                            "ladder_min_size": float(min_size),
                            "support_requested": count,
                            "union_names": union,
                            "union_fits": union <= room,
                            "attempts": attempts,
                        }
                        return w, log | supports[key] | rung
        if best:
            # A book whose union with the held names fits beats any that does
            # not; only when none fits does the objective alone decide.
            fits = [b for b in best if b[5] <= union_room]
            obj, key, w, log, live, union, strict = min(fits or best, key=lambda b: b[0])
            rung = {"ladder_gross": key[1], "ladder_min_size": key[2], "support_requested": key[0],
                    "union_names": union, "union_fits": union <= union_room, "attempts": attempts,
                    "chosen_by": "best objective over feasible supports (gross cap)"}
            return w, log | supports[key] | rung
    return None, {"status": "no rung within slack tolerance", "attempts": attempts} | extra


# E6 step 1 (D18): HHRZ 2018 sec. 2.5 decile sort inside the eligible pool,
# within each sector (D18 amendment 1: global tails leave sectors one-sided,
# lesson 45). Decile 9 = top. vw: the sector's NYSE breakpoints; ew: names
# below the NYSE 20th percentile of me dropped, breakpoints from all remaining
# names. A sector with fewer than 10 reference names uses all its names.
def hhrz_deciles(c: pd.DataFrame, nyse_me: pd.Series, weighting: str) -> tuple[pd.DataFrame, pd.Series]:
    if weighting == "ew":
        micro = float(nyse_me.quantile(0.2)) if len(nyse_me) else 0.0
        c = c[c["me"] >= micro]
    elif weighting != "vw":
        raise ValueError(weighting)
    nyse = pd.Series(c.index.isin(nyse_me.index) if len(nyse_me) else True, index=c.index)
    ref = nyse if weighting == "vw" else pd.Series(True, index=c.index)
    dec = pd.Series(0, index=c.index)
    for _, g in c.groupby("sector"):
        r = g.loc[ref.loc[g.index], "mu"]
        base = (r if len(r) >= 10 else g["mu"]).to_numpy()
        bps = np.quantile(base, np.linspace(0.1, 0.9, 9))
        dec.loc[g.index] = np.searchsorted(bps, g["mu"].to_numpy(), side="right")
    return c, dec


# Paper reference weights: g/2 a side, by me (vw) or equal (ew), clipped to
# each name's cap with the excess spread over the names below it.
def _side_ref(size: pd.Series, caps: pd.Series, total: float) -> pd.Series:
    w = pd.Series(0.0, index=size.index)
    free, left = size.index, total
    for _ in range(50):
        if left <= 1e-12 or free.empty:
            break
        x = left * size.loc[free] / size.loc[free].sum()
        over = x > caps.loc[free]
        if not over.any():
            w.loc[free] += x
            break
        hit = free[over.to_numpy()]
        w.loc[hit] = caps.loc[hit]
        left = total - float(w.sum())
        free = free.difference(hit)
    return w


# The paper's spread portfolio: top decile long, bottom decile (short_ok) short,
# gross/2 a side, me-weighted (vw) or equal (ew), capped per name.
def hhrz_reference(c: pd.DataFrame, dec: pd.Series, weighting: str, gross: float) -> pd.Series:
    size = c["me"] if weighting == "vw" else pd.Series(1.0, index=c.index)
    ref_l = c.index[(dec == 9).to_numpy()]
    ref_s = c.index[((dec == 0) & c["short_ok"].astype(bool)).to_numpy()]
    return pd.concat([_side_ref(size.loc[ref_l], c.loc[ref_l, "cap"], gross / 2),
                      -_side_ref(size.loc[ref_s], c.loc[ref_s, "cap_short"], gross / 2)])


# E6: step 1 fixes names and signs by expected return (deciles, hysteresis
# for held names, union room), step 2 reweights them for minimum risk, beta
# and costs at mu'w >= rho x mu'w_ref; then gross scales down if predicted
# vol exceeds step.vol_cap. The floor steps down (rho ladder) before gross.
FLOOR_LADDER = (0.75, 0.5, 0.0)
# Net is held by the hard +-0.5 band inside solve_qp (its penalty pulls it to 0
# where free); beta must sit in its band. Sector/size/style slack is logged (D18).
E6_TOL = {"beta": 1e-6}


def two_step_book(f: Formation, m: Final, step: Step) -> tuple[pd.Series | None, dict]:
    from fiam.v4b.risk import model as risk_model

    p = m.policy
    c = _candidates(f, m, step)
    c, dec = hhrz_deciles(c, f.nyse_me, step.weighting)
    held = f.w_pre[f.w_pre.abs() > 1e-9]
    hl = held[held > 0].index.intersection(c.index)
    hs = held[held < 0].index.intersection(c.index)
    longs = c.index[(dec == 9).to_numpy()].union(hl[(dec.loc[hl] >= 8).to_numpy()])
    shorts = c.index[((dec == 0) & c["short_ok"].astype(bool)).to_numpy()]
    shorts = shorts.union(hs[((dec.loc[hs] <= 1) & c.loc[hs, "short_ok"].astype(bool)).to_numpy()])
    # Extremeness: percentile distance from the side's end (smaller = more extreme).
    pct = c["mu"].rank(pct=True)
    ext = pd.concat([1 - pct.loc[longs], pct.loc[shorts]])
    order = ext.sort_values().index
    room = m.hard.names_max - NAMES_HEADROOM
    union_room = m.hard.names_max - UNION_HEADROOM
    live = set(held.index)
    keep, trimmed = [], 0
    for n in order:  # most extreme first; held names are already in the union, entries use its room
        if len(keep) >= room:
            trimmed += 1
            continue
        if n not in live and len(live | set(keep) | {n}) > union_room:
            trimmed += 1
            continue
        keep.append(n)
    # names_min is a hard rule and wins over the union room (logged as union_fits).
    if len(keep) < m.hard.names_min:  # thin month: next-most-extreme names, both sides
        more_l = 1 - pct[(dec == 8).to_numpy()].drop(longs, errors="ignore")
        more_s = pct[((dec == 1) & c["short_ok"].astype(bool)).to_numpy()].drop(shorts, errors="ignore")
        extra = pd.concat([more_l, more_s]).sort_values().index[: m.hard.names_min - len(keep)]
        keep += list(extra)
        longs = longs.union(extra.intersection(more_l.index))
        shorts = shorts.union(extra.intersection(more_s.index))
    names = pd.Index(keep)
    signs = pd.Series(np.where(names.isin(longs), 1.0, -1.0), index=names)
    log0 = {"eom": str(f.eom.date()), "step": step.name, "selected": int(len(names)),
            "longs": int((signs > 0).sum()), "shorts": int((signs < 0).sum()), "trimmed": trimmed,
            "held_kept": int(len(set(names) & live)), "pool": int(len(c))}
    attempts = []
    for gross in (p.target_gross, *GROSS_LADDER):
        if gross > p.target_gross:
            continue
        trial = dataclasses.replace(m, policy=dataclasses.replace(p, target_gross=float(gross)))
        w_ref = hhrz_reference(c, dec, step.weighting, gross)
        mu_ref = float(f.mu.reindex(w_ref.index).fillna(0.0) @ w_ref)
        for rho in (step.floor_rho, *FLOOR_LADDER):
            floor = rho * max(mu_ref, 0.0)
            w, log = solve_qp(f, trial, step, names, signs, floor=floor)
            ok = w is not None and all((log.get("slacks") or {}).get(k, 0.0) <= t for k, t in E6_TOL.items())
            attempts.append({"gross": float(gross), "rho": rho, "status": log.get("status"), "ok": ok})
            if not ok:
                continue
            vol = risk_model.vol(f.snap, w)
            if vol > step.vol_cap:  # one rescale of gross to the vol cap, same floor share
                g2 = gross * step.vol_cap / vol
                trial = dataclasses.replace(m, policy=dataclasses.replace(p, target_gross=float(g2)))
                w2, log2 = solve_qp(f, trial, step, names, signs, floor=rho * max(mu_ref, 0.0) * g2 / gross)
                if w2 is not None:
                    w, log, gross = w2, log2, g2
                    vol = risk_model.vol(f.snap, w)
            w = w[w.abs() >= 0.25 * p.position_min]
            beta = float(f.snap["beta"].reindex(w.index).fillna(1.0) @ w)
            mu_w = float(f.mu.reindex(w.index).fillna(0.0) @ w)
            return w, log | log0 | {
                "ladder_gross": float(gross), "rho": rho, "mu_ref": mu_ref, "mu_w": mu_w,
                "pred_vol": float(vol), "pred_beta": beta, "live_names": int(len(w)),
                "union_names": int(len(live | set(w.index))),
                "union_fits": len(live | set(w.index)) <= union_room, "attempts": attempts}
    return None, log0 | {"status": "no E6 solve", "attempts": attempts}


# Hurdle N in {250, 300, 450}: maximise predicted IR at the frozen IC with
# measured per-N costs (CONTINUATION §2.1 formula, mechanics not a race).
def hurdle_pick(
    ic: float,
    costs: dict[int, float],
    pool: int = 1862,
    gross: float = 1.8,
    omega: float = 0.259,
    tc: float = 0.6,
    infl: float = 1.5,
    premium: float = 0.04,
) -> tuple[int, dict]:
    nd = NormalDist()
    table = {}
    for n, c in costs.items():
        p = n / 2 / pool
        ez = nd.pdf(nd.inv_cdf(1 - p)) / p
        per_ic = gross * tc * omega * math.sqrt(12) * ez
        te = gross * omega / math.sqrt(n) * infl
        table[n] = {
            "ir": float((per_ic * ic - premium - c) / te),
            "ic_needed": float((premium + c) / per_ic),
            "cost": c,
        }
    return max(table, key=lambda n: table[n]["ir"]), table
