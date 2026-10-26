# Frozen E-LASSO forecasts for the single 2021+ evaluation.
#
# The validation run stopped at 2020-12-31. Extending the authors' R code over
# 2021-2026 would refit coefficients on the evaluation returns, which is not a
# forecast: it is an in-sample replay. This module applies the last frozen
# coefficient rows (2020-12-31) to later characteristic cross-sections. The
# features still use the same GHZ transform as build_input.py, but no
# post-2020 label enters the coefficients or the forecast at any date.
#
# This is deliberately a static model. It is the only honest way to produce a
# 2021+ forecast from the frozen E-LASSO artifact without rerunning the authors'
# rolling estimation on the evaluation window.

from pathlib import Path

import numpy as np
import pandas as pd

from fiam.v4b.elasso.build_input import ghz
from fiam.v4b.forecast import data

BASE = Path(__file__).resolve().parents[1] / "out" / "elasso"
RUN = BASE / "run"
OUT = BASE / "run_oos"
COEF_CUT = pd.Timestamp("2020-12-31")
LAST_EOM = pd.Timestamp("2026-07-31")


def _dated(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"]).astype("datetime64[ns]")
    return out


def features(
    cut: pd.Timestamp = pd.Timestamp("2026-08-31"),
    first_eom: pd.Timestamp = COEF_CUT,
    last_eom: pd.Timestamp = LAST_EOM,
    keep=None,
) -> pd.DataFrame:
    """The authors' one-month-lagged input, without requiring a future label.

    Row date t carries characteristics known at the prior eom and the return
    earned in t. For the OOS forecast we only need the characteristics, so the
    final row can be a month whose label is not in the panel yet.
    """
    chars = data.characteristics()
    p = data.panel(cut=cut)
    p = p.join(data.tradable(p))
    p = p[p["long_ok"] & (p["me"] > 0)].copy()
    if keep is not None:  # the same screen as the training rows (walkforward --universe)
        p = p[keep(p)].copy()
    p = p[p["eom"].between(first_eom, last_eom)].copy()
    ex = pd.read_parquet(
        data.PANEL,
        columns=["permno", "eom", "exchcd"],
        filters=[("eom", ">=", first_eom), ("eom", "<=", last_eom)],
    )
    ex["eom"] = pd.to_datetime(ex["eom"]).astype("datetime64[ns]")
    p = p.merge(ex, on=["permno", "eom"], how="left")
    z = pd.DataFrame({c: ghz(p, c) for c in chars}, index=p.index)
    z = z.fillna(0.0)
    front = pd.DataFrame(
        {
            "date": (p["eom"] + pd.offsets.MonthEnd(1)).dt.date,
            "permno": p["permno"].astype("int64"),
            "exchcd": p["exchcd"].astype("float64"),
            "me": p["me"].astype("float64"),
            "ret": (p["ret_exc_lead1m"] * 100.0).astype("float64"),
        }
    )
    return pd.concat([front, z], axis=1).sort_values(
        ["date", "permno"], ignore_index=True
    )


def _coef(name: str) -> pd.DataFrame:
    return _dated(pd.read_parquet(RUN / f"{name}.parquet"))


def _row_at(frame: pd.DataFrame, cut: pd.Timestamp) -> pd.Series:
    rows = frame[frame["date"] <= cut]
    if rows.empty:
        raise ValueError(f"no coefficient row on or before {cut}")
    return rows.sort_values("date").iloc[-1]


def _avg(frame: pd.DataFrame, cut: pd.Timestamp, window: float) -> pd.Series:
    rows = frame[frame["date"] <= cut].sort_values("date")
    if window == np.inf:
        use = rows
    else:
        use = rows.tail(int(window))
    return use.drop(columns="date").mean()


def frozen(
    data_in: pd.DataFrame, coef_cut: pd.Timestamp = COEF_CUT
) -> pd.DataFrame:
    """Apply the last frozen S-, C- and E-LASSO coefficients to each row.

    The authors' combination is fitted on month-t forecasts and next-month
    returns. Freezing at 2020-12 uses the last fitted combination, then applies
    it unchanged to every OOS month. No future coefficient row is read.
    """
    coef_lasso = _coef("coefLasso")
    coef_int = _coef("coefUniIntercept")
    coef_slope = _coef("coefUniSlope")
    coef_gr = _coef("coefGr")
    coef_enc = _coef("coefEncompass")
    chars = [c for c in coef_lasso.columns if c not in ("date", "intercept")]
    missing = sorted(set(chars) - set(data_in.columns))
    if missing:
        raise ValueError(f"OOS input is missing characteristics: {missing[:5]}")

    z = data_in[chars].to_numpy(dtype=float)
    s_coef = {
        name: _avg(coef_lasso, coef_cut, window)
        for name, window in (
            ("Ma1", 1),
            ("Ma36", 36),
            ("Ma60", 60),
            ("Ma120", 120),
            ("MaInf", np.inf),
        )
    }
    s_forecast = {
        name: b["intercept"] + z @ b[chars].to_numpy(dtype=float)
        for name, b in s_coef.items()
    }

    int_row = _row_at(coef_int, coef_cut)
    slope_row = _row_at(coef_slope, coef_cut)
    gr_row = _row_at(coef_gr, coef_cut)
    univariate = (
        int_row[chars].to_numpy(dtype=float)
        + z * slope_row[chars].to_numpy(dtype=float)
    )
    selected = gr_row[chars].to_numpy(dtype=float) != 0.0
    if selected.sum() == 0:
        c_forecast = np.zeros(len(data_in))
    else:
        c_forecast = univariate[:, selected].mean(axis=1)

    enc_row = _row_at(coef_enc, coef_cut)
    out = data_in[["date", "permno", "exchcd", "me", "ret"]].copy()
    for name in ("Ma1", "Ma36", "Ma60", "Ma120", "MaInf"):
        weight = float(enc_row[name])
        out[name] = (1.0 - weight) * s_forecast[name] + weight * c_forecast
    return out


def main() -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    f = features()
    out = frozen(f)
    out.to_parquet(OUT / "forecastElasso_oos.parquet", index=False)
    # A small provenance record: the coefficient cutoff and the selected
    # univariate count, not a performance claim.
    gr = _row_at(_coef("coefGr"), COEF_CUT)
    enc = _row_at(_coef("coefEncompass"), COEF_CUT)
    pd.Series(
        {
            "coef_cut": str(COEF_CUT.date()),
            "first_target": str(pd.to_datetime(out["date"]).min().date()),
            "last_target": str(pd.to_datetime(out["date"]).max().date()),
            "rows": int(len(out)),
            "selected_univariate": int((gr.drop("date") != 0).sum()),
            "encompass_MaInf": float(enc["MaInf"]),
        }
    ).to_json(OUT / "provenance.json", indent=2)
    return out


if __name__ == "__main__":
    d = main()
    print(d.shape, d["date"].min(), d["date"].max(), d.groupby("date").size().median())
