# The crowd score: where AI agents picking for retail clients would buy, learned from their picks.

import json

import lightgbm as lgb
import pandas as pd

from fiam import book as P
from fiam import data, paths

PICKS = paths.EXHIBITS / "agents" / "crowd_picks.parquet"
CACHE = P.CACHE / "crowd.parquet"
OUT = paths.EXHIBITS / "crowd.json"

# What an agent sees of each stock: plain labels over percentiles, never a name or a date.
CARD = {
    "1-year momentum": "ret_12_1",
    "last month": "ret_1_0",
    "volatility": "rvol_21d",
    "size": "market_equity",
    "book to price": "be_me",
    "earnings yield": "ni_me",
    "sales growth": "sale_gr1",
    "profitability": "gp_at",
    "asset growth": "at_gr1",
    "share issuance": "chcsho_12m",
    "quality": "qmj",
}
EVENTS = {
    "earnings release": "item_202_earnings",
    "acquisition": "item_201_acquisition",
    "leadership change": "item_502_management_change",
    "new contract": "item_101_contract",
    "impairment": "item_205_impairment",
    "auditor change": "item_401_auditor_change",
    "restatement warning": "item_402_nonreliance",
    "news release": "item_701_regfd",
}
PARAMS = dict(
    objective="regression",
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=5 if paths.SMOKE else 200,
    num_threads=4,
    seed=42,
    deterministic=True,
    force_row_wise=True,
    verbosity=-1,
)


# Every screened stock-month as a card: percentiles from 0 to 100, and that month's 8-K events.
def cards(first: str = "2015-01-31", last: str = "2026-07-31") -> pd.DataFrame:
    frame = data.features([*CARD.values(), *EVENTS.values(), "prc", "me"])
    frame = frame[frame["eom"].between(first, last)]
    frame = frame[(frame["prc"].abs() >= 5.0) & (frame["me"] >= 300.0)].copy()
    for label, column in CARD.items():
        pct = frame.groupby("eom")[column].rank(pct=True) * 100
        frame[label] = pct.round().fillna(50).astype(int)
    for label, column in EVENTS.items():
        frame[label] = frame[column].fillna(0).gt(0).astype(int)
    return frame[[*data.KEYS, *CARD, *EVENTS]].reset_index(drop=True)


# Each month's information coefficient of a score against the next month's return.
def ic_by_year(frame: pd.DataFrame, score: str) -> dict:
    ic = (
        frame.dropna(subset=["ret_exc_lead1m"])
        .groupby("eom")[[score, "ret_exc_lead1m"]]
        .corr(method="spearman")
    )
    monthly = ic.xs(score, level=1)["ret_exc_lead1m"]
    return {str(y): float(v.mean()) for y, v in monthly.groupby(monthly.index.year)}


# Learns what the agents buy, scores every month, and measures betting against it.
def main() -> None:
    if not PICKS.exists():
        print("skipped: the crowd agent has not run yet, so there is no crowd score")
        return
    picks = pd.read_parquet(PICKS)
    picks["eom"] = picks["eom"].astype("datetime64[s]")
    rate = picks.groupby(data.KEYS)["picked"].mean().rename("rate").reset_index()
    both = picks.pivot_table(index=data.KEYS, columns="model", values="picked")
    agreement = float(both.corr().iloc[0, 1]) if both.shape[1] > 1 else None

    table = cards()
    cols = [*CARD, *EVENTS]
    train = table.merge(rate, on=data.KEYS)
    model = lgb.train(PARAMS, lgb.Dataset(train[cols], label=train["rate"]), 200)
    table["crowd_score"] = model.predict(table[cols], num_threads=PARAMS["num_threads"])
    table[[*data.KEYS, "crowd_score"]].to_parquet(CACHE, index=False)

    returns = data.panel(["ret_exc_lead1m"])
    scored = table.merge(returns, on=data.KEYS, how="left")
    scored["against_the_crowd"] = -scored["crowd_score"]
    gain = model.feature_importance("gain")
    summary = dict(
        what="Local models, acting as AI assistants picking stocks for retail clients, chose from "
        "anonymous cards each month of 2016-2020. A small model learns what they buy, so every "
        "month through 2026 gets a crowd score with no LLM at run time.",
        picks=int(len(picks)),
        models=sorted(picks["model"].unique()),
        pick_rate=float(picks["picked"].mean()),
        agreement_between_models=agreement,
        what_the_crowd_likes={c: float(g / max(gain.sum(), 1e-12)) for c, g in zip(cols, gain)},
        against_the_crowd_ic_by_year=ic_by_year(scored, "against_the_crowd"),
        note="2016-2020 are the months the agents picked in; 2021-2026 they never saw.",
    )
    OUT.write_text(json.dumps(P.round_floats(summary), indent=2), encoding="utf-8", newline="\n")
    print(f"  crowd score learned from {len(picks):,} picks; agreement {agreement}")
    print(f"  against the crowd, IC by year: {summary['against_the_crowd_ic_by_year']}")


if __name__ == "__main__":
    main()
