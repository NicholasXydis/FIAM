# Factor risk model: sectors, five styles, fiam.vol specific, from 2017.

import json
import sys

import numpy as np
import pandas as pd
from scipy import stats as st

from fiam import book as P
from fiam import data, vol
from fiam.freeze import FROZEN

STYLES = {"size": "market_equity", "value": "be_me", "momentum": "ret_12_1"}
STYLES |= {"low_vol": "ivol_capm_252d", "quality": "ope_be"}
HALF_LIFE, MIN_MONTHS = 36, 24
FACTORS = FROZEN / "risk_factor_returns.parquet"
REPORT = FROZEN / "risk_check.json"


# The eligible panel with each style as a monthly rank z and the sector.
def exposures(first: str = "2015-01-31", last: str = P.LAST_FORECAST) -> pd.DataFrame:
    extra = tuple(c for c in STYLES.values() if c not in ("market_equity", "be_me", "ret_12_1"))
    df = P.screen(P.load_panel((*extra, "ivol_capm_252d")), first, last)
    for name, col in STYLES.items():
        df[name] = P.rank_z(df, col).fillna(0.0)
    return df


# The design matrix: one column per sector and per style.
def design(df: pd.DataFrame) -> pd.DataFrame:
    sectors = pd.get_dummies(df["sector"], prefix="s", dtype=float)
    return pd.concat([sectors, df[list(STYLES)]], axis=1)


# Monthly factor returns from a cross-section regression on sqrt(me).
def factor_returns(df: pd.DataFrame) -> pd.DataFrame:
    x = design(df)
    rows = {}
    for eom, idx in df.groupby("eom").groups.items():
        y = df.loc[idx, "ret_exc_lead1m"]
        ok = y.notna()
        if ok.sum() < 100:
            continue
        w = np.sqrt(df.loc[idx, "me"].clip(lower=1.0))[ok].to_numpy()
        xm = x.loc[idx][ok].to_numpy() * w[:, None]
        coef, *_ = np.linalg.lstsq(xm, y[ok].to_numpy() * w, rcond=None)
        rows[eom] = coef
    return pd.DataFrame.from_dict(rows, orient="index", columns=x.columns).sort_index()


# A decision's covariance, realized returns only, half-life 36 months.
def covariance(returns: pd.DataFrame, eom: pd.Timestamp) -> pd.DataFrame | None:
    known = returns[returns.index < eom].fillna(0.0)
    if len(known) < MIN_MONTHS:
        return None
    weights = 0.5 ** (np.arange(len(known))[::-1] / HALF_LIFE)
    weights /= weights.sum()
    centred = known - (known * weights[:, None]).sum()
    return (centred * weights[:, None]).T @ centred


# A book's predicted monthly vol: factor part plus fiam.vol's specific.
def predicted_vol(weights: pd.Series, month: pd.DataFrame, cov: pd.DataFrame) -> float:
    rows = month.set_index("permno").reindex(weights.index)
    x = design(rows.reset_index()).reindex(columns=cov.columns, fill_value=0.0).to_numpy()
    w = weights.to_numpy()
    factor = (w @ x) @ cov.to_numpy() @ (x.T @ w)
    specific = vol.forecast(rows.reset_index()).to_numpy() ** 2
    return float(np.sqrt(factor + (w**2 * np.nan_to_num(specific)).sum()))


# Bias, VaR exceptions and Kupiec and Christoffersen tests for a book.
def check(realized: pd.Series, predicted: pd.Series) -> dict:
    both = pd.concat([realized, predicted], axis=1, keys=["r", "p"]).dropna()
    z = both["r"] / both["p"]
    out = dict(months=int(len(both)), bias=float(z.std()), band=float(np.sqrt(2 / max(len(z), 1))))
    for level in (0.95, 0.99):
        hits = (z < st.norm.ppf(1 - level)).astype(int).to_numpy()
        n, x, p = len(hits), int(hits.sum()), 1 - level
        rate = x / n if n else 0.0
        kupiec = -2 * (
            (n - x) * np.log(1 - p)
            + x * np.log(p)
            - ((n - x) * np.log(1 - rate) + x * np.log(rate))
            if 0 < x < n
            else 0.0
        )
        pairs = list(zip(hits[:-1], hits[1:]))
        n01 = sum(a == 0 and b == 1 for a, b in pairs)
        n11 = sum(a == 1 and b == 1 for a, b in pairs)
        n0, n1 = sum(a == 0 for a, _ in pairs), sum(a == 1 for a, _ in pairs)
        pi0, pi1, pi = n01 / max(n0, 1), n11 / max(n1, 1), (n01 + n11) / max(n0 + n1, 1)

        # Log-likelihood of k exceptions in m months, for Christoffersen's test.
        def ll(q, k, m):
            return k * np.log(q) + (m - k) * np.log(1 - q) if 0 < q < 1 else 0.0

        christoffersen = -2 * (ll(pi, n01 + n11, n0 + n1) - ll(pi0, n01, n0) - ll(pi1, n11, n1))
        out[f"var_{int(level * 100)}"] = dict(
            exceptions=x,
            expected=round(n * p, 1),
            kupiec_p=float(1 - st.chi2.cdf(kupiec, 1)),
            christoffersen_p=float(1 - st.chi2.cdf(christoffersen, 1)),
        )
    return out


# Factor returns frozen once, then predicted vs realized vol per book.
def main() -> None:
    from fiam import v2

    df = exposures()
    returns = factor_returns(df)
    FROZEN.mkdir(exist_ok=True)
    returns.reset_index(names="eom").to_parquet(FACTORS, index=False)
    report = dict(
        protocol="docs/protocols/risk.md section 2", specific="fiam.vol (HAR: LGBM failed)"
    )
    for name in ("v1@1e7", "v2@1e7"):
        for tag in ("check", "record"):
            folder = v2.OUT / name / tag
            if not (folder / "holdings.parquet").exists():
                continue
            held = data.read(folder / "holdings.parquet")
            book = pd.read_csv(folder / "returns.csv", parse_dates=["holding_month"])
            realized = book.set_index("forecast_eom")["gross"]
            realized.index = pd.to_datetime(realized.index)
            predicted = {}
            for eom, w in held.groupby("eom"):
                cov = covariance(returns, eom)
                if cov is not None:
                    month = df[df["eom"] == eom]
                    predicted[eom] = predicted_vol(w.set_index("permno")["weight"], month, cov)
            report[f"{name} {tag}"] = check(realized, pd.Series(predicted))
    REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main() if sys.argv[1:] != ["check"] else print(REPORT.read_text(encoding="utf-8"))
