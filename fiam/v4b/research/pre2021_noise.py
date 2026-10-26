"""Pre-2021-only noise and hurdle inputs. Reads no label after 2020-12."""

import sys

import numpy as np
import pandas as pd


def main():
    PANEL = sys.argv[1]
    COLS = [
        "permno",
        "eom",
        "me",
        "prc",
        "ret_exc_lead1m",
        "ivol_capm_252d",
        "ret_12_1",
        "gp_at",
        "o_score",
        "noa_at",
        "at_gr1",
        "oaccruals_at",
        "chcsho_12m",
        "eqnetis_at",
        "niq_at",
        "ppeinv_gr1a",
        "dolvol_126d",
    ]
    SIGNS = {
        "o_score": -1,
        "chcsho_12m": -1,
        "eqnetis_at": -1,
        "oaccruals_at": -1,
        "noa_at": -1,
        "ret_12_1": 1,
        "gp_at": 1,
        "at_gr1": -1,
        "niq_at": 1,
        "ppeinv_gr1a": -1,
    }

    df = pd.read_parquet(PANEL, columns=COLS)
    df["eom"] = pd.to_datetime(df["eom"])
    # Label month t+1 must end by 2020-12-31, so eom <= 2020-11-30
    df = df[(df["eom"] >= "2015-01-31") & (df["eom"] <= "2020-11-30")]
    df = df[(df["me"] >= 600) & (df["prc"].abs() >= 5)].copy()

    # SYY-10 style composite: within-month signed rank-z, mean of present
    z = []
    for c, s in SIGNS.items():
        z.append(s * df.groupby("eom")[c].rank(pct=True).sub(0.5))
    Z = pd.concat(z, axis=1)
    df["syy"] = Z.mean(axis=1).where(Z.notna().sum(axis=1) >= 5)

    def ic_series(col):
        out = {}
        for eom, m in df.groupby("eom"):
            ok = m[[col, "ret_exc_lead1m"]].dropna()
            if len(ok) >= 100:
                out[eom] = ok[col].rank().corr(ok["ret_exc_lead1m"].rank())
        return pd.Series(out)

    print(
        "months", df["eom"].nunique(), "names/month median", int(df.groupby("eom").size().median())
    )
    for col in ["syy", "ret_12_1", "gp_at", "o_score"]:
        s = ic_series(col)
        v = s[s.index >= "2019-01-31"]
        print(
            f"{col:10s} IC mean {s.mean():+.4f} sd {s.std():.4f} "
            f"t {s.mean() / s.std() * np.sqrt(len(s)):+.2f} | 2019-20 n {len(v)} "
            f"mean {v.mean():+.4f} se {v.std() / np.sqrt(len(v)):.4f}"
        )
        yr = s.groupby(s.index.year).mean()
        print("   by year", " ".join(f"{y}:{x:+.3f}" for y, x in yr.items()))

    iv = df.groupby("eom")["ivol_capm_252d"].median()
    print(
        "ivol_capm_252d median over months",
        round(float(iv.median()), 4),
        "(if daily, annual =",
        round(float(iv.median()) * np.sqrt(252), 3),
        ")",
    )
    adv = df.groupby("eom")["dolvol_126d"].median()
    print("dolvol_126d median $/day", round(float(adv.median()) / 1e6, 2), "m")


if __name__ == "__main__":
    main()
