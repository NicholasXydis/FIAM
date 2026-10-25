# Carbon Arc spend data: match names, build and test the signal.

import difflib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

from fiam import data
from fiam.exhibits.labels import normalise

OUT = Path("out") / "v2" / "carbon_arc"
# Our notes give Carbon Arc no publication lag, so the 30 days applies.
LAG_DAYS = 30
SURE, MAYBE = 0.95, 0.80


# Any spend table, columns named on the command line, as entity-date.
def load(path: str, name: str, date: str, value: str) -> pd.DataFrame:
    raw = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    out = raw[[name, date, value]].set_axis(["entity", "date", "spend"], axis=1)
    out["date"] = pd.to_datetime(out["date"])
    return out.dropna()


# Our names at their latest month, normalised as the label checks do.
def our_names() -> pd.DataFrame:
    names = data.features(["company_name", "ticker"]).dropna(subset=["company_name"])
    latest = names.sort_values("eom").drop_duplicates("permno", keep="last")
    return latest.assign(key=latest["company_name"].map(normalise))


# Each entity's top three matches: sure, maybe (LLM decides) or none.
def match(entities: pd.Series, ours: pd.DataFrame) -> pd.DataFrame:
    keys = ours["key"].tolist()
    by_key = ours.drop_duplicates("key").set_index("key")
    rows = []
    for entity in entities.unique():
        key = normalise(entity)
        found = difflib.get_close_matches(key, keys, n=3, cutoff=MAYBE)
        best = found[0] if found else None
        score = difflib.SequenceMatcher(None, key, best).ratio() if best else 0.0
        verdict = "sure" if score >= SURE else "maybe" if best else "none"
        permno = int(by_key.loc[best, "permno"]) if best else None
        rows.append(dict(entity=entity, permno=permno, score=score, verdict=verdict, top3=found))
    return pd.DataFrame(rows)


# Close calls (0.80 to 0.95) go to the local model, else are dropped.
def confirm(matches: pd.DataFrame, ours: pd.DataFrame) -> pd.DataFrame:
    from fiam.agents import harness as H

    maybe = matches["verdict"] == "maybe"
    if not maybe.any():
        return matches
    names = ours.drop_duplicates("permno").set_index("permno")
    schema = dict(type="object", properties=dict(same=dict(type="boolean")), required=["same"])
    try:
        with H.Server("gemma") as server:
            for i in matches.index[maybe]:
                row = names.loc[matches.at[i, "permno"]]
                question = (
                    "Are these the same company? Names from different sources differ in spelling, "
                    "abbreviations and legal suffixes. Answer with same true or false.\n"
                    f"A: {matches.at[i, 'entity']}\nB: {row['company_name']} ({row['ticker']})"
                )
                reply = server.chat([dict(role="user", content=question)], schema=schema)
                same = H.parse(reply).get("same") is True
                matches.at[i, "verdict"] = "llm yes" if same else "llm no"
    except (OSError, RuntimeError) as exc:
        print(f"no model for the close calls ({exc}); they are dropped", flush=True)
    return matches


# Spend growth, last three months on a year before, known 30 days on.
def signal(spend: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    kept = matches[matches["verdict"].isin(["sure", "llm yes"])][["entity", "permno"]]
    monthly = spend.merge(kept, on="entity")
    monthly["month"] = monthly["date"] + pd.offsets.MonthEnd(0)
    monthly = monthly.groupby(["permno", "month"])["spend"].sum().unstack("permno").sort_index()
    recent = monthly.rolling(3).sum()
    growth = (recent / recent.shift(12) - 1).stack().rename("spend_growth").reset_index()
    growth["eom"] = growth["month"] + pd.DateOffset(days=LAG_DAYS) + pd.offsets.MonthEnd(0)
    return growth.drop(columns="month")


# The protocol's test: spend minus sales growth on next sales surprise.
def test(growth: pd.DataFrame) -> dict:
    panel = data.features(["saleq_gr1", "saleq_su"])
    frame = growth.merge(panel, on=data.KEYS)
    frame["signal"] = frame["spend_growth"] - frame["saleq_gr1"]
    # The next report's surprise, the first saleq_su change in four months.
    future = panel.set_index(data.KEYS)["saleq_su"].unstack("permno").sort_index()
    ahead = future.shift(-3).stack().rename("next_surprise").reset_index()
    frame = frame.merge(ahead, on=data.KEYS).dropna(subset=["signal", "next_surprise"])
    ic = frame.groupby("eom")[["signal", "next_surprise"]].corr(method="spearman")
    monthly = ic.xs("signal", level=1)["next_surprise"].dropna()
    t = None
    if len(monthly) > 4:
        # Newey-West, lag 3: the 3-month target overlaps across months.
        fit = sm.OLS(monthly.to_numpy(), np.ones(len(monthly))).fit(
            cov_type="HAC", cov_kwds={"maxlags": 3}
        )
        t = float(fit.tvalues[0])
    return dict(
        months=len(monthly),
        ic=float(monthly.mean()) if len(monthly) else None,
        t=t,
        passed=bool(t is not None and monthly.mean() > 0 and t > 2),
    )


# A fake file in the likely shape: our names misspelt, two years' spend.
def fake(path: Path, names: int = 300, seed: int = 42) -> None:
    rng = np.random.default_rng(seed)
    ours = our_names().sample(names, random_state=seed)
    rows = []
    for _, r in ours.iterrows():
        label = str(r["company_name"]).title().replace(" Inc", ", Inc.")
        level = rng.uniform(1e5, 1e7)
        for month in pd.date_range("2024-01-31", "2026-07-31", freq="ME"):
            rows.append(dict(company=label, date=month, card_spend=level * rng.lognormal(0, 0.1)))
    pd.DataFrame(rows).to_csv(path, index=False)


# Matches, builds and tests the signal, or rehearses on a fake file.
def main(args: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if args[:1] == ["dry-run"]:
        path = OUT / "fake_spend.csv"
        fake(path)
        args = [str(path), "company", "date", "card_spend"]
    spend, ours = load(*args[:4]), our_names()
    matches = confirm(match(spend["entity"], ours), ours)
    matches.to_csv(OUT / "matches.csv", index=False)
    kept = matches[matches["verdict"].isin(["sure", "llm yes"])]
    kept.sample(min(50, len(kept)), random_state=42).to_csv(OUT / "check_by_hand.csv", index=False)
    growth = signal(spend, matches)
    growth.to_parquet(OUT / "signal.parquet", index=False)
    report = dict(entities=len(matches), verdicts=matches["verdict"].value_counts().to_dict())
    report |= dict(test=test(growth), human_check="check_by_hand.csv: 50 matches, precision")
    (OUT / "report.json").write_text(
        json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
