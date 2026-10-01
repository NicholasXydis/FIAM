# The scorer: learning-to-rank what a neutral book earns, one model per tail, averaged over seeds.


import lightgbm as lgb
import numpy as np
import pandas as pd

from fiam import book as P
from fiam import data, paths
from fiam.ml import dataset as D
from fiam.ml import teachers as TE
from fiam.ml import text as T

OUT = paths.EXHIBITS / "scorer.json"
CACHE = P.CACHE / "scores.parquet"
CROWD = P.CACHE / "crowd.parquet"
# What the triage and analyst agents made of each stock-month's filings, as small models learned
# them from pre-2021 answers; the analyst's own verdicts never enter.
TRIAGE, ANALYST = P.CACHE / "triage.parquet", P.CACHE / "analyst.parquet"
PREDS = P.CACHE / "preds" / "scorer.parquet"

# Two years before the rules' first test year, so its forecasts can be scaled on earlier years.
FIRST_YEAR = 2025 if paths.SMOKE else 2019
SEEDS = (42,) if paths.SMOKE else (42, 43, 44, 45, 46)
ROUNDS, PATIENCE = (20, 5) if paths.SMOKE else (1000, 50)

# LambdaRank on month groups. Fixed settings; only the number of rounds is read off validation.
PARAMS = dict(
    objective="lambdarank",
    metric="ndcg",
    eval_at=[100],
    lambdarank_truncation_level=100,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=1000,
    feature_fraction=0.7,
    bagging_fraction=0.7,
    bagging_freq=1,
    lambda_l2=10.0,
    num_threads=4,
    deterministic=True,
    force_row_wise=True,
    verbosity=-1,
)


# Characteristics, 8-K counts, teacher outputs and, once the crowd agent has run, its score.
def inputs() -> tuple[pd.DataFrame, list[str]]:
    frame, cols = TE.inputs()
    sectors = data.features(["gics"])
    sectors["sector"] = sectors.pop("gics").astype("string").str[:2].fillna("XX")
    frame = frame.merge(sectors, on=data.KEYS, how="left")
    for path in (TE.CACHE, CROWD, TRIAGE, ANALYST):
        if path.exists():
            extra = data.read(path)
            frame = frame.merge(extra, on=data.KEYS, how="left")
            cols += [c for c in extra.columns if c not in data.KEYS]
    return frame.sort_values(["holding_month", "permno"], ignore_index=True), cols


# The exposures a stock picker's return must be free of: beta and the five style characteristics.
STYLE = ["beta_60m", *P.FACTORS]


# Next month's return less its sector's mean and its beta and style, by least squares each month.
def residual(frame: pd.DataFrame) -> pd.Series:
    month = frame["holding_month"]
    target = frame[D.TARGET] - frame.groupby([month, frame["sector"]])[D.TARGET].transform("mean")
    out = pd.Series(np.nan, index=frame.index)
    for _, rows in frame.groupby(month).groups.items():
        y = target.loc[rows]
        known = y.notna().to_numpy()
        if known.sum() <= len(STYLE) + 1:
            continue
        x = np.c_[np.ones(known.sum()), frame.loc[rows[known], STYLE].to_numpy()]
        fit = np.linalg.lstsq(x, y[known].to_numpy(), rcond=None)[0]
        out.loc[rows[known]] = y[known].to_numpy() - x @ fit
    return out


# Deciles of the residual return within each month, 0 worst to 9 best.
def deciles(frame: pd.DataFrame) -> np.ndarray:
    pct = residual(frame).groupby(frame["holding_month"]).rank(pct=True, method="first")
    return np.minimum((pct * 10).astype(int), 9).to_numpy()


# One ranker for one tail: labels as they are for the top, reversed for the bottom.
def ranker(train: pd.DataFrame, validate: pd.DataFrame, cols: list[str], top: bool, seed: int):
    # One month per group, labelled for this tail.
    def dataset(part: pd.DataFrame) -> lgb.Dataset:
        label = deciles(part) if top else 9 - deciles(part)
        groups = part.groupby("holding_month", sort=True).size().to_numpy()
        return lgb.Dataset(part[cols], label=label, group=groups)

    return lgb.train(
        {**PARAMS, "seed": seed},
        dataset(train),
        ROUNDS,
        valid_sets=[dataset(validate)],
        callbacks=[lgb.early_stopping(PATIENCE, verbose=False)],
    )


# One test year: both tails, every seed, averaged as within-month ranks.
def fit_year(frame: pd.DataFrame, cols: list[str], year: int, text=None) -> pd.DataFrame:
    m = frame["holding_month"]
    start = pd.Timestamp(year=year, month=1, day=1)
    val_start = start - pd.DateOffset(years=D.VAL_YEARS)
    # Text components fitted on this fold's training years only.
    if text is not None:
        parts = T.components(text, (m < val_start).to_numpy())
        frame = frame.assign(**{n: parts[:, i] for i, n in enumerate(T.NAMES)})
        cols = [*cols, *T.NAMES]
    train = D.labelled(frame[(m >= D.FIRST_TARGET) & (m < val_start)])
    validate = D.labelled(frame[(m >= val_start) & (m < start)])
    test = frame[(m.dt.year == year) & (m <= D.LAST_HOLDING_MONTH)]
    out = test[[*data.KEYS, "holding_month", D.TARGET]].copy()
    per_seed = []
    for seed in SEEDS:
        top = ranker(train, validate, cols, True, seed)
        bottom = ranker(train, validate, cols, False, seed)
        raw = top.predict(test[cols]) - bottom.predict(test[cols])
        out[f"seed_{seed}"] = (
            pd.Series(raw, index=test.index).groupby(test["holding_month"]).rank(pct=True)
        )
        per_seed.append(f"seed_{seed}")
    out["score"] = out[per_seed].mean(axis=1) - 0.5
    return out


# Scores every test year, then writes the scores and their IC.
def main() -> None:
    frame, cols = inputs()
    text = T.aligned(frame)
    years = range(FIRST_YEAR, D.LAST_TEST_YEAR + 1)
    scored = pd.concat([fit_year(frame, cols, y, text) for y in years], ignore_index=True)
    scored[[*data.KEYS, "holding_month", "score"]].to_parquet(CACHE, index=False)

    # The rules' years in the shape the OOS R-squared step reads, every model the same way.
    book_years = scored[scored["holding_month"].dt.year >= D.FIRST_TEST_YEAR]
    preds = book_years.rename(columns={"score": "pred", D.TARGET: "actual"})
    PREDS.parent.mkdir(parents=True, exist_ok=True)
    preds[[*data.KEYS, "holding_month", "pred", "actual"]].to_parquet(PREDS, index=False)

    ic = P.information_coefficient(preds)
    by_year = {
        str(y): P.information_coefficient(g)["ic_mean"]
        for y, g in preds.groupby(preds["holding_month"].dt.year)
    }
    seeds = {
        s: P.information_coefficient(book_years.rename(columns={s: "pred", D.TARGET: "actual"}))
        for s in scored.columns
        if s.startswith("seed_")
    }
    summary = dict(
        what="Two LightGBM LambdaRank models per test year, one for each tail, trained on the "
        "rules' folds to rank next month's return net of sector, beta and style, averaged over "
        "seeds. "
        "Scores for 2019-2020 only scale the 2021 forecasts for the out-of-sample R-squared.",
        features=len(cols),
        uses_crowd_score=CROWD.exists(),
        uses_text=text is not None,
        uses_triage=TRIAGE.exists(),
        uses_analyst=ANALYST.exists(),
        ic_2021_2026=ic,
        ic_by_year=by_year,
        ic_by_seed={k: v["ic_mean"] for k, v in seeds.items()},
        # Every scored year, 2019-2020 included, for the learning curve.
        ic_every_year={
            str(y): P.information_coefficient(
                g.rename(columns={"score": "pred", D.TARGET: "actual"})
            )["ic_mean"]
            for y, g in scored.groupby(scored["holding_month"].dt.year)
        },
    )
    paths.write_json(OUT, summary)
    print(f"  scorer IC {ic['ic_mean']:.4f} (t {ic['ic_t']:.2f}), by year {by_year}")


if __name__ == "__main__":
    main()
