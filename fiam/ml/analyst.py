# The analyst's verdicts up to November 2020 learned from what it read, then applied to every
# month, so no language model's reading of 2021-2026 reaches the book (amendment 12).

import lightgbm as lgb
import numpy as np
import pandas as pd

from fiam import book as P
from fiam import data, paths
from fiam.agents import analyst as A
from fiam.ml import crowd as C
from fiam.ml import text as T

OUT = paths.EXHIBITS / "analyst_learned.json"
CACHE = P.CACHE / "analyst.parquet"
# The last decision whose verdict may teach: the month before the evaluation's first decision.
LAST_TAUGHT = pd.Timestamp("2020-11-30")
PARAMS = dict(
    objective="regression",
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=5 if paths.SMOKE else 20,
    feature_fraction=0.5,
    num_threads=4,
    seed=42,
    deterministic=True,
    force_row_wise=True,
    verbosity=-1,
)
ROUNDS, FOLDS = 20 if paths.SMOKE else 300, 5


# The verdicts a model may learn from: answered, and dated before the evaluation's decisions.
def taught(verdicts: pd.DataFrame) -> pd.DataFrame:
    return verdicts[verdicts["analyst_conviction"].notna() & (verdicts["eom"] <= LAST_TAUGHT)]


# What the analyst read, as numbers: its material filings' FinBERT vectors and the stock's card.
def features(vectors: pd.DataFrame) -> pd.DataFrame:
    filings = A.material()[["document_id", *data.KEYS]]
    joined = filings.merge(vectors, on="document_id").drop(columns="document_id")
    monthly = joined.groupby(data.KEYS).mean().reset_index()
    return monthly.merge(C.cards(), on=data.KEYS, how="left")


# Mean monthly rank correlation of a score with next month's return, t over months of 10 or more.
def against_returns(frame: pd.DataFrame, score: str) -> dict:
    both = frame[["eom", score, "active"]].dropna()
    monthly = both.groupby("eom")[[score, "active"]].apply(
        lambda g: g[score].corr(g["active"], method="spearman") if len(g) >= 10 else np.nan
    )
    monthly = monthly.dropna()
    t = monthly.mean() / monthly.std() * np.sqrt(len(monthly)) if len(monthly) > 1 else np.nan
    return dict(
        months=int(len(monthly)),
        stock_months=int(len(both)),
        rank_correlation=float(monthly.mean()),
        t=float(t),
    )


def main() -> None:
    vectors = T.saved_vectors()
    if not A.CONVICTIONS.exists() or vectors is None:
        CACHE.unlink(missing_ok=True)
        print("skipped: needs the analyst's verdicts and the FinBERT vectors")
        return
    verdicts = data.read(A.CONVICTIONS)
    table = features(vectors)
    del vectors
    # Text components fitted on the months that teach, so later filings never shape them.
    columns = [f"v{i}" for i in range(T.WIDTH)]
    early = (table["eom"] <= LAST_TAUGHT).to_numpy()
    parts = T.components(table[columns].to_numpy(dtype=np.float32), early)
    table = table.drop(columns=columns).assign(**{n: parts[:, i] for i, n in enumerate(T.NAMES)})
    cols = [*T.NAMES, *C.CARD, *C.EVENTS]
    labelled = taught(verdicts).merge(table, on=data.KEYS)
    if len(labelled) < 10 * FOLDS:
        CACHE.unlink(missing_ok=True)
        print(f"skipped: only {len(labelled)} verdicts before 2021 have vectors, too few")
        return

    x, y = labelled[cols], labelled["analyst_conviction"].to_numpy(dtype=float)
    fold = np.random.default_rng(42).permutation(len(y)) % FOLDS
    unseen = np.zeros(len(y))
    for k in range(FOLDS):
        model = lgb.train(PARAMS, lgb.Dataset(x[fold != k], label=y[fold != k]), ROUNDS)
        unseen[fold == k] = model.predict(x[fold == k], num_threads=PARAMS["num_threads"])
    model = lgb.train(PARAMS, lgb.Dataset(x, label=y), ROUNDS)
    table["analyst_hat"] = model.predict(table[cols], num_threads=PARAMS["num_threads"])
    table[[*data.KEYS, "analyst_hat"]].to_parquet(CACHE, index=False)

    # The recall test: the analyst's own verdicts beside the small model's, on the same months.
    returns = data.panel(["ret_exc_lead1m"])
    returns["active"] = returns["ret_exc_lead1m"] - returns.groupby("eom")[
        "ret_exc_lead1m"
    ].transform("mean")
    answered = verdicts[verdicts["analyst_conviction"].notna()]
    judged = answered.merge(table[[*data.KEYS, "analyst_hat"]], on=data.KEYS)
    judged = judged.merge(returns[[*data.KEYS, "active"]], on=data.KEYS, how="left")
    periods = {"2015-2020": judged["eom"] <= LAST_TAUGHT, "2021-2026": judged["eom"] > LAST_TAUGHT}
    summary = dict(
        what="The analyst agent's verdicts up to November 2020, learned by a small model from the "
        "FinBERT vectors of the material filings it read and the stock's card, then applied to "
        "every stock-month with a material filing. Only this model's output feeds the scorer; no "
        "language model's reading of 2021-2026 reaches the book.",
        taught_on=int(len(labelled)),
        cross_validated_rank_correlation=float(pd.Series(unseen).corr(pd.Series(y), "spearman")),
        scored_stock_months=int(len(table)),
        recall_test={
            name: dict(
                analyst=against_returns(judged[rows], "analyst_conviction"),
                learned=against_returns(judged[rows], "analyst_hat"),
            )
            for name, rows in periods.items()
        },
        reading="Mean monthly rank correlation with next month's return, on the same answered "
        "stock-months, t across months. If the "
        "analyst beats the small model by far more in 2021-2026 than in 2015-2020, the gap is "
        "recall. In 2015-2020 the small model was fitted to these same verdicts.",
    )
    paths.write_json(OUT, summary)
    print(
        f"  analyst learned from {len(labelled):,} verdicts before 2021, "
        f"{len(table):,} stock-months scored; recall test {summary['recall_test']}"
    )


if __name__ == "__main__":
    main()
