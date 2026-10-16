# Scores the honesty tests (docs/protocols/honesty.md, amendment 1): accuracy, flip rates, the
# memorization difference-in-differences and re-identification, from the saved calls only.

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as st

from fiam import data, freeze
from fiam.agents import harness as H
from fiam.agents import honesty as A

OUT = Path("out") / "v2" / "honesty.json"
REPS, SEED = 10_000, 42
# Stated before any result: the smallest accuracy gap 250 per side detects at 80% power.
MDE = 0.125


# Each filing's 2-day abnormal return: the stock's total return less the S&P 500 over the first
# trading day on or after the filing date and the next.
def abnormal(chosen: pd.DataFrame) -> pd.Series:
    daily = data.research("daily_market", ["permno", "date", "total_return"])
    daily = daily[daily["permno"].isin(chosen["permno"])].astype({"total_return": float})
    by_name = {
        p: g.set_index("date")["total_return"].sort_index() for p, g in daily.groupby("permno")
    }
    market = freeze.market_daily()
    out = {}
    for _, row in chosen.iterrows():
        r = by_name.get(row["permno"])
        if r is None:
            continue
        days = r[r.index >= row["filing_date"]].iloc[:2]
        m = market.reindex(days.index)
        if len(days) == 2 and m.notna().all():
            out[row["document_id"]] = float((1 + days).prod() - (1 + m).prod())
    return pd.Series(out, name="abnormal")


# One row per filing: each condition's call, whether it was right, and the re-identification.
def table() -> pd.DataFrame:
    chosen = A.sample()
    calls = pd.read_json(H.RUNS / "honesty.jsonl", lines=True)
    wide = calls[calls["condition"] != "identify"].pivot_table(
        index="document_id", columns="condition", values="call", aggfunc="first"
    )
    found = calls[calls["condition"] == "identify"].set_index("document_id")["correct"]
    df = chosen.set_index("document_id")[["side", "filing_date", "permno"]].join(wide)
    df = df.join(found.rename("identified")).join(abnormal(chosen))
    for c in ("masked", "named", "reversed", "dated", "repeat"):
        df[f"{c}_right"] = (df[c] == "up") == (df["abnormal"] > 0)
    return df[df["abnormal"].notna()]


# Bootstrap of a statistic over filings, resampled within each side: estimate and 95% interval.
def interval(df: pd.DataFrame, statistic) -> dict:
    rng, sides = np.random.default_rng(SEED), [g for _, g in df.groupby("side")]
    draws = [
        statistic(pd.concat(g.iloc[rng.integers(len(g), size=len(g))] for g in sides))
        for _ in range(REPS)
    ]
    low, high = np.quantile(draws, [0.025, 0.975])
    return dict(estimate=float(statistic(df)), ci95=[float(low), float(high)])


def did(df: pd.DataFrame) -> float:
    gap = (df["named_right"].astype(float) - df["masked_right"]).groupby(df["side"]).mean()
    return float(gap["before"] - gap["after"])


def flip_gap(df: pd.DataFrame) -> float:
    return float((df["reversed"] != df["masked"]).mean() - (df["repeat"] != df["masked"]).mean())


def main() -> None:
    df = table()
    out = dict(filings=df["side"].value_counts().to_dict(), minimum_detectable_gap=MDE)
    out["accuracy"] = {
        side: {
            c: dict(
                share=float(g[f"{c}_right"].mean()),
                p_vs_half=float(st.binomtest(int(g[f"{c}_right"].sum()), len(g), 0.5).pvalue),
            )
            for c in ("masked", "named", "reversed", "dated", "repeat")
        }
        for side, g in df.groupby("side")
    }
    out["flip_rate"] = {
        side: dict(
            reversed=float((g["reversed"] != g["masked"]).mean()),
            repeat=float((g["repeat"] != g["masked"]).mean()),
        )
        for side, g in df.groupby("side")
    }
    out["flip_gap_reversed_minus_repeat"] = interval(df, flip_gap)
    out["memorization_did"] = interval(df, did)
    out["reidentification"] = {
        side: dict(
            share=float(g["identified"].mean()),
            p_vs_chance=float(
                st.binomtest(int(g["identified"].sum()), len(g), 0.2, "greater").pvalue
            ),
        )
        for side, g in df.dropna(subset=["identified"]).groupby("side")
    }
    month = df["filing_date"].dt.to_period("M").astype(str)
    out["masked_accuracy_by_month"] = df.groupby(month)["masked_right"].mean().to_dict()
    out["null_model"] = "ChronoGPT was not run; the protocol's fallback applies and is reported."
    OUT.write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("filings", "memorization_did", "reidentification")}))


if __name__ == "__main__":
    main()
