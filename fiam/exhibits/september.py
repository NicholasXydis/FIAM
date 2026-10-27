# The September 2026 book, the shipped code one month past the record.

import hashlib
import sys
from pathlib import Path

import pandas as pd

from fiam import book as P
from fiam import costs as C
from fiam import data, paths
from fiam.freeze import FROZEN

DECISION = pd.Timestamp("2026-08-31")
V1 = FROZEN / "september_v1.csv"
V2 = FROZEN / "september_v2.csv"
V3 = FROZEN / "september_v3.csv"
FINAL = FROZEN / "september_final.csv"


# The shipped universe plus one decision month, built like the record's.
def universe() -> pd.DataFrame:
    return P.shipped(
        P.build_signal(P.screen(P.load_panel(), P.FIRST_FORECAST, str(DECISION.date())))
    )


# Walks each month so August drifts into September; keeps every book.
def walk_to_september(
    universe: pd.DataFrame, optimize=P.optimize_month, model=C.DEFAULT, track=None
) -> dict:
    books = {}
    for step in P.walk(universe, optimize, True, model):
        month, weights, info, _, parts, _ = step
        books[month] = (weights, info, parts)
        if track is not None:
            track(P.month_record(*step))
    return books


# A book as a trader reads it: name, ticker, weight, largest first.
def table(weights: pd.Series, info: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        dict(
            permno=weights.index,
            ticker=info.loc[weights.index, "ticker"].to_numpy(),
            company_name=info.loc[weights.index, "company_name"].to_numpy(),
            weight=weights.round(8).to_numpy(),
        )
    )
    return out.sort_values("weight", key=abs, ascending=False, ignore_index=True)


# August must match the submission (in percent) for September to follow.
def check_august(books: dict) -> float:
    holdings = pd.read_csv(paths.HOLDINGS).query("Date == '2026-08-01'")
    shipped = holdings.set_index("PERMNO")["WEIGHT"] / 100
    august = books[DECISION - pd.offsets.MonthEnd(1)][0]
    both = pd.concat([shipped, august], axis=1).fillna(0.0)
    return float((both.iloc[:, 0] - both.iloc[:, 1]).abs().max())


# A book frozen as CSV with its SHA-256, so any later change shows.
def write(book: pd.DataFrame, path) -> str:
    FROZEN.mkdir(exist_ok=True)
    book.to_csv(path, index=False, lineterminator="\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


# Drifted August to September trades at $10M, days to fill at 10% ADV.
def trade_list(books: dict, crowd: pd.Series | None = None) -> pd.DataFrame:
    august = DECISION - pd.offsets.MonthEnd(1)
    w_aug, info_aug, parts_aug = books[august]
    rf = P.benchmarks().set_index("month")["rf"].get(pd.Timestamp("2026-09-01"), 0.0)
    before = P.drift(w_aug, info_aug, parts_aug, rf)
    target, info = books[DECISION][:2]
    idx = target.index.union(before.index)
    quotes = info.reindex(idx).combine_first(info_aug.reindex(idx))
    trade = target.reindex(idx, fill_value=0.0) - before.reindex(idx, fill_value=0.0)
    dollars = trade.abs() * P.NAV
    out = pd.DataFrame(
        dict(
            ticker=quotes["ticker"],
            company_name=quotes["company_name"],
            current_weight=before.reindex(idx, fill_value=0.0),
            target_weight=target.reindex(idx, fill_value=0.0),
            trade_weight=trade,
            shares=(trade * P.NAV / quotes["prc"].abs()).round(),
            pct_adv=dollars / quotes["dolvol_126d"],
            days_at_10pct=dollars / (0.10 * quotes["dolvol_126d"]),
            days_at_10pct_at_1bn=trade.abs() * 1e9 / (0.10 * quotes["dolvol_126d"]),
        )
    )
    if crowd is not None:
        out["crowd_score"] = crowd.reindex(idx)
    # A blank name or ticker takes the latest known one for that stock.
    labels = data.features(["ticker", "company_name"]).dropna().sort_values("eom")
    latest = labels.drop_duplicates("permno", keep="last").set_index("permno")
    for col in ("ticker", "company_name"):
        out[col] = out[col].fillna(latest[col].reindex(out.index))
    out = out[out["trade_weight"].abs() > 1e-6].rename_axis("permno").reset_index()
    return out.sort_values("trade_weight", key=abs, ascending=False, ignore_index=True)


# September's AI crowd scores from the frozen model (level 0, no GPU).
def crowd_scores() -> pd.Series | None:
    from fiam.exhibits import crowd_lab as X

    if not X.EMULATOR.exists():
        return None
    month = X.ranks(str(DECISION.date()), str(DECISION.date()))
    return pd.Series(X.crowd_score(month).to_numpy(), index=month["permno"])


# The shipped book, checked on August, or a switched book by its name.
def main(which: str = "v1") -> None:
    if which in ("v2", "v3", "final"):
        from functools import partial

        from fiam import v2

        on = dict(v2=v2.V2, v3=v2.final(), final=v2.final_three())[which]
        settings = v2.Settings(on)
        frame = v2.universe((P.FIRST_FORECAST, str(DECISION.date())), settings, v2.params())
        v2.reset()
        optimize = partial(v2.optimize, settings=settings)
        learns = partial(v2.observe, settings=settings) if which != "v2" else None
        books = walk_to_september(frame, optimize, track=learns)
        path = dict(v2=V2, v3=V3, final=FINAL)[which]
    else:
        books = walk_to_september(universe())
        gap = check_august(books)
        if gap > 1e-6:
            raise SystemExit(f"August differs from the submitted holdings by up to {gap:.2e}")
        path = V1
    book = table(*books[DECISION][:2])
    digest = write(book, path)
    trades = trade_list(books, crowd_scores())
    trades.to_csv(Path("out") / "v2" / f"trade_list_{which}.csv", index=False)
    gross, net = book["weight"].abs().sum(), book["weight"].sum()
    print(f"September {which}: {len(book)} names, gross {gross:.3f}, net {net:+.4f}, {digest[:16]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
