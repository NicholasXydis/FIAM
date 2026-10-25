# The triage agent's labels learned from FinBERT, then put on every 8-K.


import lightgbm as lgb
import numpy as np
import pandas as pd

from fiam import book as P
from fiam import data, paths
from fiam.ml import text as T

OUT = paths.EXHIBITS / "triage.json"
LABELS = paths.EXHIBITS / "agents" / "triage_labels.parquet"
FILINGS, MONTHLY = P.CACHE / "triage_filings.parquet", P.CACHE / "triage.parquet"
KINDS = ["routine", "good", "bad", "distress"]
PARAMS = dict(
    objective="multiclass",
    num_class=len(KINDS),
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


# A classifier on the labelled vectors and its out-of-fold accuracy.
def learn(x: np.ndarray, y: np.ndarray) -> tuple[lgb.Booster, float]:
    fold = np.random.default_rng(42).permutation(len(y)) % FOLDS
    hits = []
    for k in range(FOLDS):
        model = lgb.train(PARAMS, lgb.Dataset(x[fold != k], label=y[fold != k]), ROUNDS)
        hits.append(np.argmax(model.predict(x[fold == k]), axis=1) == y[fold == k])
    return lgb.train(PARAMS, lgb.Dataset(x, label=y), ROUNDS), float(np.concatenate(hits).mean())


# Learns from the agent's sample, labels all 8-Ks, saves monthly counts.
def main() -> None:
    vectors = T.saved_vectors()
    if not LABELS.exists() or vectors is None:
        print("skipped: needs the triage agent's labels and the FinBERT vectors")
        return
    # An answer the model cut off is left out, and counted in the summary.
    answered = pd.read_parquet(LABELS)
    unreadable = int((~answered["label"].isin(KINDS)).sum())
    labels = answered[answered["label"].isin(KINDS)].merge(vectors, on="document_id")
    if len(labels) < 5 * FOLDS:
        print(f"skipped: only {len(labels)} labelled filings have vectors, too few to learn from")
        return
    columns = [f"v{i}" for i in range(T.WIDTH)]
    y = labels["label"].map({k: i for i, k in enumerate(KINDS)}).to_numpy()
    model, accuracy = learn(labels[columns].to_numpy(), y)
    texts = data.research("filing_text", ["document_id", *data.KEYS])
    scored = texts.merge(vectors, on="document_id")
    kind = np.argmax(model.predict(scored[columns].to_numpy()), axis=1)
    filings = scored[["document_id", *data.KEYS]].assign(label=np.array(KINDS)[kind])
    filings.to_parquet(FILINGS, index=False)
    counts = pd.crosstab([filings["permno"], filings["eom"]], filings["label"])
    counts = counts.reindex(columns=KINDS, fill_value=0).add_prefix("triage_").reset_index()
    counts.to_parquet(MONTHLY, index=False)
    by_year = filings.groupby(filings["eom"].dt.year)["label"].value_counts(normalize=True)
    summary = dict(
        what="An agent's labels on a fixed sample of masked 8-Ks from 2015-2018, learned from "
        "FinBERT vectors and applied to every filing; counts per stock-month feed the scorer.",
        labelled=int(len(labels)),
        unreadable=unreadable,
        labelled_by_kind=labels["label"].value_counts().to_dict(),
        cross_validated_accuracy=accuracy,
        share_by_year={str(y): g.droplevel(0).to_dict() for y, g in by_year.groupby(level=0)},
    )
    paths.write_json(OUT, summary)
    print(f"  triage: accuracy {accuracy:.1%} on unseen labels, {len(filings):,} filings labelled")


if __name__ == "__main__":
    main()
