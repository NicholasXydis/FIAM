# Lazy Prices: annual reports that change a lot (Cohen-Malloy-Nguyen).

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer

from fiam.v4 import data, sources
from fiam.v4.signals import base

# A similar report is good news, a changed one bad: taken as is.
SIGN = 1
# The previous report of the same form, filed 300 to 500 days earlier.
GAP = (300, 500)
# A score carries 12 months from its report's first close.
CARRY = pd.DateOffset(months=12)
ITEMS = ("item1a", "item7")
# Lower-case words of 2+ letters; counts hashed into 2^20 slots.
VECTORS = HashingVectorizer(
    token_pattern=r"[a-z]{2,}", lowercase=True, alternate_sign=False, norm="l2", n_features=2**20
)


# Each report and the same filer's previous one of its form, if any.
def pairs() -> pd.DataFrame:
    meta = pd.concat(sources.read_parts("sections", ["cik", "form", "filing_date"]))
    reports = meta.drop_duplicates("accession").sort_values(["filing_date", "accession"])
    prior = reports.rename(columns={"accession": "prior", "filing_date": "prior_date"})
    reports["latest_prior"] = reports["filing_date"] - pd.Timedelta(days=GAP[0])
    got = pd.merge_asof(
        reports, prior[["cik", "form", "prior", "prior_date"]].sort_values(["prior_date", "prior"]),
        left_on="latest_prior", right_on="prior_date", by=["cik", "form"], direction="backward",
    )  # fmt: skip
    gap = (got["filing_date"] - got["prior_date"]).dt.days
    return got[gap.between(*GAP)][["accession", "prior"]]


# The mean cosine of Item 1A and Item 7 with the prior report.
def scores(log: dict) -> pd.DataFrame:
    p = pairs()
    need = set(p["accession"]) | set(p["prior"])
    vecs = {}
    for part in sources.read_parts("sections", list(ITEMS)):
        part = part[part["accession"].isin(need)].drop_duplicates("accession")
        both = part.dropna(subset=list(ITEMS))
        if both.empty:
            continue
        for item in ITEMS:
            mat = VECTORS.transform(both[item].tolist())
            for i, acc in enumerate(both["accession"]):
                vecs[(acc, item)] = mat[i]
    rows = []
    for acc, prior in p.itertuples(index=False):
        sims = [vecs[(acc, i)].multiply(vecs[(prior, i)]).sum()
                for i in ITEMS if (acc, i) in vecs and (prior, i) in vecs]  # fmt: skip
        if len(sims) == len(ITEMS):
            rows.append((acc, float(np.mean(sims))))
    log["report_pairs"], log["scored"] = len(p), len(rows)
    return pd.DataFrame(rows, columns=["accession", "score"])


# The latest score public by T within 12 months, per stock.
def build(eoms, log: dict | None = None) -> pd.DataFrame:
    log = {} if log is None else log
    s = scores(log)
    meta = pd.concat(sources.read_parts("sections", ["form"]))[
        ["accession", "permno", "first_close"]
    ]
    s = s.merge(meta, on="accession").sort_values(["first_close", "accession"], kind="stable")
    out = []
    for eom, T in base.formations(eoms).itertuples(index=False):
        live = s[(s["first_close"] <= T) & (s["first_close"] > T - CARRY)]
        last = live.drop_duplicates("permno", keep="last")
        data.assert_public_by(last["first_close"], T, "Lazy Prices")
        out.append(last[["permno", "accession"]].assign(eom=eom, value=last["score"].to_numpy()))
    return pd.concat(out, ignore_index=True)
