# The monthly controller's QP, relax-and-round and greedy support.

import dataclasses
import math
from dataclasses import dataclass, field

import cvxpy as cp
import numpy as np
import pandas as pd

from fiam.vfinal.config import Policy, Step
from fiam.vfinal.risk import parts as riskparts

# Exact-penalty weights on policy slacks: tier 1 >> tier 2 >> alpha.
M1, M2 = 5.0, 1.0
# The extra betas' band; the optimiser prices a 5-session trade.
EXTRA_BETA_BAND, EXEC_DAYS = 0.05, 5
# Reference TE for style bands; the stage-0 vol guardrail.
SIGMA_REF, SIGMA_MAX = 0.04, 0.15
# Slack beyond this is a failed formation at that gross.
SLACK_TOL = {"net": 1e-6, "sector_max": 1e-6, "beta": 1e-6, "size": 1e-6}
# Names kept free for the execution overlap of exits and entries.
NAMES_HEADROOM, UNION_HEADROOM = 60, 10
GROSS_LADDER = (1.5, 1.2, 1.0, 0.8, 0.6, 0.4)
# Fees: IBKR Pro, CAT, SEC Section 31 and FINRA TAF (2026-09-30).
COMMISSION, COMMISSION_MIN, COMMISSION_MAX = 0.005, 1.00, 0.01
SEC_RATE, TAF_PER_SHARE, TAF_MAX, CAT_PER_SHARE = 27.80e-6, 0.000195, 9.79, 0.000003
PRICE_MISSING = 10.0


# Everything one formation's solve reads, knowable at the eom close.
@dataclass
class Formation:
    eom: pd.Timestamp
    mu: pd.Series
    snap: dict
    adv: pd.Series
    half_spread: pd.Series
    borrow: pd.Series
    coverage: pd.Series
    sigma: pd.Series
    price: pd.Series
    w_pre: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    nav: float = 1e9
    horizon: int = 21


# A usable price for per-share fees: a bad one counts as $10.
def _price(price) -> np.ndarray:
    p = np.abs(np.asarray(price, dtype=float))
    return np.where(np.isfinite(p) & (p > 0.5), p, PRICE_MISSING)


# Fee per dollar traded either side (commission + CAT), convex form.
def per_dollar(price) -> np.ndarray:
    return (COMMISSION + CAT_PER_SHARE) / _price(price)


# Extra fee per dollar sold (SEC + TAF), convex form.
def per_dollar_sold(price) -> np.ndarray:
    return SEC_RATE + TAF_PER_SHARE / _price(price)


# Exact fees in dollars for one order at a raw price (fees.order).
def order_fee(dollars: float, price: float, sell: bool) -> float:
    dollars = abs(float(dollars))
    if dollars <= 0:
        return 0.0
    shares = dollars / float(_price(price))
    fee = min(max(COMMISSION * shares, COMMISSION_MIN), COMMISSION_MAX * dollars)
    fee += CAT_PER_SHARE * shares
    if sell:
        fee += SEC_RATE * dollars + min(TAF_PER_SHARE * shares, TAF_MAX)
    return fee


# Per-name cap: the policy cap, five days at 10% ADV, the hard cap.
def position_caps(f: Formation, p: Policy) -> pd.Series:
    liq = p.participation * f.adv * p.days_to_exit_max / f.nav
    return liq.clip(upper=p.position_cap).clip(upper=p.name_cap)


# Short caps: the asymmetric short cap under the symmetric cap.
def short_caps(p: Policy, caps: np.ndarray) -> np.ndarray:
    return np.minimum(caps, p.position_cap_short)


# The square-root law over EXEC_DAYS in return units (impact_cost).
def impact_cost(q, sigma, adv, nav, impact_y):
    q = np.abs(np.asarray(q, dtype=float))
    adv = np.maximum(np.asarray(adv, dtype=float), 1.0)
    return impact_y * np.asarray(sigma, float) * np.sqrt(nav / (EXEC_DAYS * adv)) * q**1.5


# A quadratic c q^2 matched to impact_cost at the average position.
def impact_quadratic_coef(sigma, adv, nav, impact_y, q_ref) -> np.ndarray:
    adv = np.maximum(np.asarray(adv, dtype=float), 1.0)
    q_ref = np.maximum(np.asarray(q_ref, dtype=float), 1e-9)
    return impact_y * np.asarray(sigma, float) * np.sqrt(nav / (EXEC_DAYS * adv)) / np.sqrt(q_ref)


# Style band half-widths in vol units: share x 4% / annual factor vol.
def band_widths(f: Formation, share: float) -> pd.Series:
    F1 = f.snap["F1"]
    ann = np.sqrt(np.diag(F1.to_numpy(dtype=float)) * 252)
    return share * SIGMA_REF / pd.Series(ann, index=F1.index).replace(0, np.nan)


# Directional specific variance: longs downside, shorts upside.
def directional_d(f: Formation, names: pd.Index, side: np.ndarray) -> np.ndarray:
    base = f.snap["d"].reindex(names).fillna(0.0).to_numpy(dtype=float)
    down = f.snap["d_down"].reindex(names).fillna(pd.Series(base, index=names)).to_numpy(float)
    up = f.snap["d_up"].reindex(names).fillna(pd.Series(base, index=names)).to_numpy(float)
    return np.maximum(np.where(np.asarray(side, float) < 0, up, down), 0.5 * base)


# Names held before the trade.
def wpre_live(w_pre: pd.Series) -> pd.Index:
    return w_pre.index[w_pre.abs() > 1e-9]


# The QP: free signs, the relaxation, or signed by side.
def solve_qp(f: Formation, p: Policy, names, signs: pd.Series | None, relax: bool = False):
    B = f.snap["B"]
    names = pd.Index([n for n in names if n in B.index and n in f.mu.index])
    # A signed name must be able to hold the minimum position.
    if signs is not None and not relax:
        caps_all = position_caps(f, p).reindex(names).fillna(0.0)
        names = names[caps_all.to_numpy() >= p.position_min]
    log = {"eom": f"{f.eom:%Y-%m-%d}", "names_in": int(len(names)), "relax": relax}
    if len(names) < p.names_min:
        return None, log | {"status": "support below names_min"}
    n, H = len(names), f.horizon
    mu = f.mu.reindex(names).fillna(0.0).to_numpy(dtype=float)
    wpre = f.w_pre.reindex(names).fillna(0.0).to_numpy(dtype=float)
    Bm = B.loc[names].to_numpy(dtype=float)
    F = f.snap["F"].reindex(index=B.columns, columns=B.columns).to_numpy(dtype=float)
    F = 0.5 * (F + F.T)
    d = f.snap["d"].reindex(names).to_numpy(dtype=float)
    # Semivariance: relax takes the lower side, signed books their own.
    if relax:
        d = np.minimum(directional_d(f, names, np.ones(n)), directional_d(f, names, -np.ones(n)))
    elif signs is not None:
        d = directional_d(f, names, signs.reindex(names).fillna(1.0).to_numpy(dtype=float))
    caps = position_caps(f, p).reindex(names).fillna(0.0).to_numpy(dtype=float)
    sc = short_caps(p, caps)
    adv = f.adv.reindex(names).fillna(0.0).to_numpy(dtype=float)
    order_cap = p.participation * adv * EXEC_DAYS / f.nav + np.abs(wpre)
    if relax:
        wp, wn = cp.Variable(n, nonneg=True), cp.Variable(n, nonneg=True)
        w = wp - wn
    else:
        w = cp.Variable(n)
    q = w - wpre
    bw = Bm.T @ w
    risk = cp.quad_form(bw, cp.psd_wrap(F)) + H * cp.sum(cp.multiply(d, cp.square(w)))
    # Stage 0 keeps the plain risk price; the rest use the vol target's.
    stage2 = signs is not None or relax
    gamma = p.vol_target_risk_aversion if stage2 else p.risk_aversion
    obj = -(mu @ w)
    if stage2:
        beta_vec = f.snap["beta"].reindex(names).fillna(1.0).to_numpy(dtype=float)
        obj = obj + p.beta_penalty * cp.square(beta_vec @ w)
    cons = [cp.abs(q) <= np.maximum(order_cap, 1e-9)]
    slacks, shadow_cons = {}, {}
    month = f.snap["month"].loc[names]
    short_ok = month["short_ok"].to_numpy(dtype=bool).astype(float)
    long_ok = month["long_ok"].to_numpy(dtype=float)
    sn = cp.Variable(nonneg=True)
    b = f.borrow.reindex(names).fillna(p.borrow_flat_other).to_numpy(dtype=float)
    # Stage 0: free sign, gross ceiling, no minimum size.
    if not stage2:
        cons += [w >= -sc * short_ok, w <= caps * long_ok, cp.norm1(w) <= p.target_gross]
    # Relax: free signs, gross a ceiling, the hard net band, borrow.
    elif relax:
        cons += [wn <= sc * short_ok, wp <= caps * long_ok, cp.sum(wp + wn) <= p.target_gross,
                 cp.abs(cp.sum(w)) <= p.net_band]  # fmt: skip
        obj = obj + (H / 252) * (b @ wn)
    # Signed: bounds by side, gross a ceiling, the hard net band, borrow.
    else:
        side = signs.reindex(names).fillna(1.0).to_numpy(dtype=float)
        lo = np.where(side > 0, p.position_min, -sc)
        hi = np.where(side > 0, caps, -p.position_min)
        cons += [w >= lo, w <= hi, side @ w <= p.target_gross, cp.abs(cp.sum(w)) <= p.net_band]
        obj = obj + (H / 252) * (np.where(side < 0, -b, 0.0) @ w)
    cons += [cp.sum(w) <= sn, -cp.sum(w) <= sn]
    obj = obj + M1 * sn
    slacks["net"] = sn
    # Trade costs: spread, quadratic impact proxy, per-share fees.
    s = f.half_spread.reindex(names).fillna(0.005).to_numpy(dtype=float)
    sig = f.sigma.reindex(names).fillna(0.02).to_numpy(dtype=float)
    q_ref = np.maximum(p.target_gross / max(n, 1), p.position_min)
    c = impact_quadratic_coef(sig, adv, f.nav, p.impact_y, q_ref)
    px = f.price.reindex(names).to_numpy(dtype=float)
    obj = obj + s @ cp.abs(q) + cp.sum(cp.multiply(c, cp.square(q)))
    obj = obj + per_dollar(px) @ cp.abs(q) + per_dollar_sold(px) @ cp.pos(-q)
    # Uncertainty: u w^2 grows where the characteristics are missing.
    cov = f.coverage.reindex(names).fillna(0.5).clip(lower=0.1).to_numpy(dtype=float)
    obj = obj + cp.sum(cp.multiply(p.uncertainty_scale * H * d / cov, cp.square(w)))
    # Bands: sectors, beta, the extra betas, size and the four styles.
    sectors = pd.get_dummies(month["sector"]).reindex(
        columns=sorted(month["sector"].dropna().unique()), fill_value=0.0
    )
    ssec = cp.Variable(len(sectors.columns), nonneg=True)
    sec_exp = sectors.to_numpy(dtype=float).T @ w
    sec_cons = [sec_exp <= p.sector_band + ssec, -sec_exp <= p.sector_band + ssec]
    cons += sec_cons
    shadow_cons["sector"] = (list(sectors.columns), sec_cons)
    sbeta = cp.Variable(nonneg=True)
    beta = f.snap["beta"].reindex(names).to_numpy(dtype=float)
    beta_cons = [beta @ w <= p.beta_band + sbeta, -beta @ w <= p.beta_band + sbeta]
    cons += beta_cons
    shadow_cons["beta"] = (["mkt"], beta_cons)
    ex = f.snap["beta_extra"].reindex(names)
    ex = ex.fillna(ex.median()).to_numpy(dtype=float)
    sextra = cp.Variable(ex.shape[1], nonneg=True)
    cons += [ex.T @ w <= EXTRA_BETA_BAND + sextra, -(ex.T @ w) <= EXTRA_BETA_BAND + sextra]
    widths, wide = band_widths(f, 0.25), band_widths(f, p.style_band_share)
    tier2 = []
    for k, col in enumerate(B.columns):
        if col not in ("size", "value", "momentum", "profitability", "investment"):
            continue
        s_k = cp.Variable(nonneg=True)
        width = widths[col] if col == "size" else wide[col]
        band = [bw[k] <= width + s_k, -bw[k] <= width + s_k]
        cons += band
        shadow_cons[col] = ([col], band)
        tier2.append(s_k)
        if col == "size":
            slacks["size"] = s_k
    obj = obj + M1 * (cp.sum(ssec) + sbeta + cp.sum(sextra)) + M2 * sum(tier2)
    slacks |= {"sector_max": ssec, "beta": sbeta, "beta_extra_max": sextra}
    # Annualised vol guardrails, base and stressed.
    var_cap = (p.vol_target if stage2 else SIGMA_MAX) ** 2 * H / 252
    cons += [risk <= var_cap]
    Fs = riskparts.stressed(f.snap["F"]).reindex(index=B.columns, columns=B.columns)
    Fs = Fs.to_numpy(dtype=float)
    risk_s = cp.quad_form(bw, cp.psd_wrap(0.5 * (Fs + Fs.T))) + H * cp.sum(
        cp.multiply(d, cp.square(w))
    )
    cons += [risk_s <= var_cap * 4]
    problem = cp.Problem(cp.Minimize(obj + 0.5 * gamma * risk), cons)
    try:
        problem.solve(solver=cp.CLARABEL)
    except cp.SolverError as exc:
        return None, log | {"status": f"solver error: {exc}"}
    if w.value is None or problem.status not in ("optimal", "optimal_inaccurate"):
        return None, log | {"status": str(problem.status)}
    out = pd.Series(np.asarray(w.value).ravel(), index=names)
    got = {k: float(np.max(v.value)) for k, v in slacks.items() if v.value is not None}
    shadows = {}
    for key, (columns, pair) in shadow_cons.items():
        value = np.atleast_1d(pair[0].dual_value) - np.atleast_1d(pair[1].dual_value)
        shadows[key] = dict(zip(columns, value.astype(float)))
    pred = float(np.sqrt(max(float(risk.value), 0.0)) * np.sqrt(252 / H))
    return out, log | {"status": problem.status, "slacks": got, "shadows": shadows,
                       "objective": float(problem.value), "pred_vol_ann": pred,
                       "pred_mu": float(mu @ out.to_numpy())}  # fmt: skip


# Eligible candidates: the $3bn floor, a forecast and a usable cap.
def candidates(f: Formation, p: Policy, step: Step) -> pd.DataFrame:
    month = f.snap["month"].copy()
    month = month[month["me"] >= step.universe_floor_musd]
    month.loc[~np.isfinite(f.borrow.reindex(month.index).to_numpy(dtype=float)), "short_ok"] = False
    month["mu"] = f.mu.reindex(month.index)
    month["cap"] = position_caps(f, p).reindex(month.index)
    month["cap_short"] = short_caps(p, month["cap"].fillna(0.0).to_numpy())
    month = month[month["mu"].notna() & (month["cap"] >= p.position_min)]
    month.loc[month["cap_short"] < p.position_min, "short_ok"] = False
    return month


# Stage 0 signs from a free-sign solve on every candidate.
def stage0_signs(f: Formation, p: Policy, c: pd.DataFrame):
    w0, log = solve_qp(f, p, c.index, None)
    signs = pd.Series(np.where(c["mu"] >= 0, 1.0, -1.0), index=c.index)
    if w0 is not None:
        live = w0[w0.abs() > 1e-6]
        signs.loc[live.index.intersection(signs.index)] = np.sign(
            live.reindex(signs.index).dropna()
        )
    signs.loc[~c["short_ok"].fillna(False).to_numpy()] = 1.0
    shadow = pd.Series(0.0, index=c.index)
    for key, values in log.get("shadows", {}).items():
        if key == "sector":
            shadow += c["sector"].map(values).fillna(0.0)
        else:
            for col, value in values.items():
                shadow += f.snap["B"][col].reindex(c.index) * value
    return signs, shadow


# Stage 1: greedy per side by (mu - borrow - entry cost) / sigma_e.
def greedy_support(f: Formation, p: Policy, step: Step):
    c = candidates(f, p, step)
    signs, shadow = stage0_signs(f, p, c)
    c["side"] = signs
    c = c[((c["side"] > 0) & c["long_ok"]) | ((c["side"] < 0) & c["short_ok"])].copy()
    c["cap"] = np.where(c["side"] < 0, c["cap_short"], c["cap"])
    sig_e = np.sqrt(np.maximum(f.snap["d"].reindex(c.index).to_numpy(), 1e-12) * f.horizon)
    borrow = f.borrow.reindex(c.index).fillna(p.borrow_flat_other).to_numpy()
    borrow_cost = np.where(c["side"] < 0, borrow * f.horizon / 252, 0.0)
    spread = f.half_spread.reindex(c.index).fillna(0.005).to_numpy()
    sig = f.sigma.reindex(c.index).fillna(0.02).to_numpy()
    adv = np.maximum(f.adv.reindex(c.index).fillna(0.0).to_numpy(), 1.0)
    ref = np.minimum(p.target_gross / max(step.names, 1), c["cap"].to_numpy())
    px = f.price.reindex(c.index).to_numpy(dtype=float)
    entry = spread + per_dollar(px) + impact_cost(ref, sig, adv, f.nav, p.impact_y)
    prior = f.w_pre.reindex(c.index).fillna(0.0).to_numpy()
    held = (prior * c["side"].to_numpy()) > 1e-9
    # Keeping a side avoids entry and saves an exit: incumbent credit.
    entry = np.where(held, 0.0, entry)
    exit_credit = np.where(
        held, spread + per_dollar(px) + impact_cost(np.abs(prior), sig, adv, f.nav, p.impact_y), 0
    )
    reduced = (c["mu"] - shadow.reindex(c.index)).to_numpy()
    c["score"] = (c["side"].to_numpy() * reduced - borrow_cost - entry + exit_credit) / sig_e
    half_n = step.names // 2
    quota = (1.5 * half_n * c["sector"].value_counts(normalize=True)).clip(lower=5).to_dict()
    chosen: list = []
    for side_val in (1.0, -1.0):
        counts, picked = {}, 0
        pool = c[c["side"] == side_val].sort_values("score", ascending=False)
        for permno, row in pool.iterrows():
            if picked >= half_n:
                break
            if counts.get(row["sector"], 0) >= quota.get(row["sector"], 5):
                continue
            chosen.append(permno)
            counts[row["sector"]] = counts.get(row["sector"], 0) + 1
            picked += 1
    chosen = sector_repair(c, chosen, p)
    chosen = sector_repair(c, exposure_repair(f, c, chosen, p), p)
    # Cap repair: top up a side whose caps cannot fund half the gross.
    chosen_set = set(chosen)
    for side_val in (1.0, -1.0):
        have = float(c.loc[c.index.isin(chosen_set) & (c["side"] == side_val), "cap"].sum())
        if have >= p.target_gross / 2:
            continue
        rest = c[(c["side"] == side_val) & ~c.index.isin(chosen_set)]
        for permno, row in rest.sort_values("score", ascending=False).iterrows():
            if len(chosen_set) >= p.names_max:
                break
            chosen_set.add(permno)
            have += float(row["cap"])
            if have >= p.target_gross / 2:
                break
    names = pd.Index(sorted(chosen_set))
    return names, signs.reindex(names)


# Exact min and max of sum(a x) with mins <= x <= caps, sum(x) = total.
def side_extremes(a: np.ndarray, caps: np.ndarray, mins: np.ndarray, total: float):
    # Fill the cheapest (or dearest) names first up to their caps.
    def fill(order):
        x, left = mins.copy(), total - mins.sum()
        for i in order:
            add = min(caps[i] - x[i], max(left, 0.0))
            x[i] += add
            left -= add
        return float(a @ x)

    up = np.argsort(a)
    return fill(up), fill(up[::-1])


# The achievable interval of an exposure under net 0 at gross G.
def exposure_interval(sel: pd.DataFrame, a: pd.Series, p: Policy) -> tuple[float, float]:
    total, parts = p.target_gross / 2, []
    for side_val in (1.0, -1.0):
        part = sel[sel["side"] == side_val]
        vals = side_val * a.reindex(part.index).fillna(0.0).to_numpy(dtype=float)
        caps = part["cap"].to_numpy(dtype=float)
        mins = np.full(len(part), p.position_min)
        if caps.sum() < total or mins.sum() > total:
            return (np.inf, -np.inf)
        parts.append(side_extremes(vals, caps, mins, total))
    return parts[0][0] + parts[1][0], parts[0][1] + parts[1][1]


# Swaps support names until the beta and size bands are reachable.
def exposure_repair(f: Formation, c: pd.DataFrame, chosen: list, p: Policy, passes: int = 60):
    widths = band_widths(f, 0.25)
    targets = [
        (f.snap["beta"], p.beta_band + SLACK_TOL["beta"]),
        (f.snap["B"]["size"], float(widths.get("size", 0.2)) + SLACK_TOL["size"]),
    ]
    chosen = list(chosen)
    for a, band in targets:
        for _ in range(passes):
            sel = c.loc[chosen]
            lo, hi = exposure_interval(sel, a, p)
            if lo <= band and hi >= -band:
                break
            too_high = lo > band
            contrib = pd.Series(sel["side"].to_numpy() * a.reindex(sel.index).fillna(0.0)
                                .to_numpy(), index=sel.index)  # fmt: skip
            pool = contrib[contrib > 0] if too_high else contrib[contrib < 0]
            if pool.empty:
                break
            drop = sel.loc[pool.index].sort_values("score").index[0]
            side_val = float(sel.at[drop, "side"])
            rest = c[(c["side"] == side_val) & ~c.index.isin(chosen)].copy()
            if rest.empty:
                break
            rest["_c"] = (side_val * a.reindex(rest.index).fillna(0.0)).to_numpy()
            rest = rest[rest["_c"] < 0] if too_high else rest[rest["_c"] > 0]
            chosen.remove(drop)
            if not rest.empty:
                chosen.append(rest.sort_values("score", ascending=False).index[0])
    return chosen


# Drops majority-side names until each sector can meet its band.
def sector_repair(c: pd.DataFrame, chosen: list, p: Policy) -> list:
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


# True when every policy slack is within its tolerance.
def slacks_ok(log: dict) -> bool:
    got = log.get("slacks") or {}
    return all(got.get(k, 0.0) <= tol for k, tol in SLACK_TOL.items())


# Entries past the union room dropped, the book re-solved (fit_union).
def fit_union(f, p: Policy, names, signs, w: pd.Series, held: set, union_room: int):
    new = [n for n in w.abs().sort_values(ascending=False).index if n not in held]
    allowed = max(union_room - len(held), 0)
    if len(new) <= allowed:
        return None
    keep = pd.Index([n for n in names if n in held or n in set(new[:allowed])])
    w2, log = solve_qp(f, p, keep, signs.reindex(keep))
    if w2 is not None:
        w2 = w2[w2.abs() >= 0.25 * p.position_min]
    return w2, log | {"entries_trimmed": len(new) - allowed}


# The greedy book: best objective over supports, gross down a ladder.
def build_book(f: Formation, p: Policy, step: Step):
    attempts, solved, best = [], {}, []
    room, union_room = p.names_max - NAMES_HEADROOM, p.names_max - UNION_HEADROOM
    held = set(wpre_live(f.w_pre))
    incumbents = len(held & set(f.mu.dropna().index))
    base = min(max(step.names, math.ceil(0.9 * incumbents)), room)
    counts = tuple(dict.fromkeys(min(base + k, room) for k in (0, 50, 100, room)))
    for gross in (p.target_gross, *GROSS_LADDER):
        if gross > p.target_gross:
            continue
        for strict in (True, False):
            for count in counts:
                for min_size in (p.position_min, 0.5 * p.position_min):
                    trial = dataclasses.replace(p, target_gross=float(gross),
                                                position_min=float(min_size))  # fmt: skip
                    key = (count, float(gross), float(min_size))
                    if key not in solved:
                        names, signs = greedy_support(
                            f, trial, dataclasses.replace(step, names=count)
                        )
                        w, log = solve_qp(f, trial, names, signs)
                        if w is not None:
                            w = w[w.abs() >= 0.25 * p.position_min]
                        if w is not None and len(held | set(w.index)) > union_room:
                            t = fit_union(f, trial, names, signs, w, held, union_room)
                            if t is not None and t[0] is not None:
                                w, log = t
                        live = int((w.abs() >= 0.5 * p.position_min).sum()) if w is not None else 0
                        union = len(held | set(w.index)) if w is not None else 0
                        solved[key] = w, log, live, union
                        attempts.append({"count": count, "gross": gross, "min_size": min_size,
                                         "status": log.get("status"), "live": live})  # fmt: skip
                    w, log, live, union = solved[key]
                    ok = (w is not None and slacks_ok(log) and p.names_min <= live <= p.names_max
                          and (union <= union_room or not strict))  # fmt: skip
                    if ok:
                        best.append((log["objective"], key, w, log, union))
        if best:
            fits = [b for b in best if b[4] <= union_room]
            obj, key, w, log, union = min(fits or best, key=lambda b: b[0])
            return w, log | {"ladder_gross": key[1], "support_requested": key[0],
                             "union_names": union, "attempts": attempts,
                             "support": "greedy"}  # fmt: skip
    return None, {"status": "no rung within slack tolerance", "attempts": attempts}


# Relax-and-round, the greedy book as its fallback.
def relax_book(f: Formation, p: Policy, step: Step):
    held = set(wpre_live(f.w_pre))
    pool = candidates(f, p, step).index.union(pd.Index(sorted(held)))
    relaxed, rlog = solve_qp(f, p, pool, None, relax=True)
    if relaxed is None:
        w, log = build_book(f, p, step)
        return w, log | {"support_fallback": f"relaxation {rlog.get('status')}"}
    big = relaxed[relaxed.abs() >= 0.5 * p.position_min]
    keep = big.abs().sort_values(ascending=False).index[: p.names_max - NAMES_HEADROOM]
    signs = np.sign(relaxed.loc[keep])
    w, log = solve_qp(f, p, keep, signs)
    if w is not None:
        w = w[w.abs() >= 0.25 * p.position_min]
        if len(held | set(w.index)) > p.names_max - UNION_HEADROOM:
            t = fit_union(f, p, keep, signs, w, held, p.names_max - UNION_HEADROOM)
            if t is not None and t[0] is not None:
                w, log = t
    live = int((w.abs() >= 0.5 * p.position_min).sum()) if w is not None else 0
    if w is None or not slacks_ok(log) or not p.names_min <= live <= p.names_max:
        gw, glog = build_book(f, p, step)
        return gw, glog | {"support_fallback": f"rounded {log.get('status')}, {live} names"}
    return w, log | {"support": "relax", "bound_objective": rlog.get("objective"),
                     "live_names": live}  # fmt: skip
