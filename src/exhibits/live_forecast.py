# The book from August 2026 data, hashed before October's returns exist. Writes live_forecast.*.

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import benchmarks as B
import paths
import pipeline as P

HOLDINGS = paths.SUBMISSION / "holdings.csv"
RETURNS = paths.SUBMISSION / "returns.csv"
OUT = paths.EXHIBITS
RECORD = OUT / "live_forecast.json"
DECISION, PRIOR = "2026-08-31", "2026-07-31"
SEALED = OUT / "live_forecast_2026-09.csv"
CORRECTED = OUT / "live_forecast_2026-09_corrected.csv"


# The September book the current code builds, and what it expects to cost.
def build() -> tuple[pd.DataFrame, dict]:
    panel = P.load_panel()
    cross = P.build_signal(P.screen(panel, DECISION, DECISION))
    prior = P.build_signal(P.screen(panel, PRIOR, PRIOR)).set_index("permno")

    # August's book after August's returns, so the trading cost starts from what we actually held.
    book = pd.read_csv(HOLDINGS, parse_dates=["Date"])
    held = book[book["Date"] == book["Date"].max()]
    august = pd.Series(held["WEIGHT"].to_numpy() / 100, index=held["PERMNO"].to_numpy())
    costs = pd.read_csv(RETURNS).iloc[-1].filter(like="cost_").to_dict()
    cash = B.benchmarks().set_index("month")["rf"].get(pd.Timestamp("2026-08-01"), 0.0)
    previous = P.drift(august, prior.reindex(august.index), costs, cash)

    step = P.rebalance(cross, previous, prior["bidaskhl_21d"])
    if step is None:
        raise RuntimeError("optimizer failed for the live month")
    weights, info, _, parts, turnover = step
    # The same limits the backtest must clear.
    assert 100 <= len(weights) <= 500, f"{len(weights)} positions"
    assert weights.abs().sum() <= 2.0 + 1e-9, "gross above 200%"
    assert abs(weights.sum()) < 0.005, "net exposure outside tolerance"

    holdings = pd.DataFrame(
        dict(
            Date=pd.Timestamp("2026-09-01"),
            PERMNO=weights.index,
            TICKER=info["ticker"].to_numpy(),
            COMPANY_NAME=info["company_name"].to_numpy(),
            WEIGHT=weights.to_numpy() * 100,
            eom=pd.Timestamp(DECISION),
        )
    )
    filled = P.fill_labels(holdings, panel)
    out = filled[["Date", "PERMNO", "TICKER", "COMPANY_NAME", "WEIGHT"]]
    out = out.rename(columns={"COMPANY_NAME": "COMPANY NAME"}).round({"WEIGHT": 6})
    facts = dict(
        positions=int(len(weights)),
        longs=int((weights > 0).sum()),
        shorts=int((weights < 0).sum()),
        gross_exposure=float(weights.abs().sum()),
        net_exposure=float(weights.sum()),
        beta_exante=float((weights * info["beta_60m"]).sum()),
        expected_cost=float(sum(parts.values())),
        turnover_one_way=float(turnover),
    )
    return out, facts


def main() -> None:
    book, facts = build()
    body = book.to_csv(index=False, lineterminator="\n").encode()
    digest = hashlib.sha256(body).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)

    # Sealed once. The hash and its date are the claim, so the first book is never rewritten.
    if RECORD.exists():
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        # The seal was taken on Windows with CRLF endings; the same rows in LF are the same book.
        same = record["sha256"] in paths.digests(body)
        if not same:
            CORRECTED.write_bytes(body)
        record["current_code"] = dict(
            what="The book today's code builds for the same month. The sealed file is unchanged.",
            identical_to_sealed=same,
            csv=None if same else CORRECTED.as_posix(),
            sha256=digest,
            code=P.source_fingerprint(),
            **facts,
        )
    else:
        SEALED.write_bytes(body)
        record = dict(
            what="Book built mechanically by the shipped code from August 2026 characteristics, "
            "the last the panel has. Scored later against public prices.",
            clean_test="October 2026, holding this book unchanged. September had begun when it "
            "was first hashed, so September is mechanical but not forecast in advance.",
            decision_month=DECISION,
            holding_month="2026-09",
            csv=SEALED.as_posix(),
            sha256=digest,
            first_hashed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **facts,
            code=P.source_fingerprint(),
        )
    RECORD.write_text(json.dumps(record, indent=2), encoding="utf-8", newline="\n")
    print(f"sealed book {record['sha256'][:16]}; today's code {digest[:16]}")


if __name__ == "__main__":
    main()
