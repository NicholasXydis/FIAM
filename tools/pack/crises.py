# The 17-crisis replay of the final book, into crises.json.

import json

import numpy as np
import pandas as pd

from tools.pack import sources as S

DECISION = pd.Timestamp("2026-08-31")
# The seventeen crisis windows of the stress exhibit.
CRISES = {
    "Dot-com peak crash": ("2000-03-10", "2000-04-14"),
    "September 11": ("2001-09-10", "2001-09-21"),
    "Accounting scandals": ("2002-07-01", "2002-07-23"),
    "Quant unwind": ("2007-07-24", "2007-08-10"),
    "Bear Stearns": ("2008-03-03", "2008-03-17"),
    "Lehman and the crash": ("2008-09-12", "2008-10-27"),
    "Junk rally, momentum crash": ("2009-03-09", "2009-05-29"),
    "US downgrade": ("2011-07-22", "2011-08-19"),
    "Taper tantrum": ("2013-05-22", "2013-06-24"),
    "China devaluation": ("2015-08-18", "2015-08-25"),
    "Oil and high-yield sell-off": ("2016-01-04", "2016-02-11"),
    "Volatility spike": ("2018-01-26", "2018-02-08"),
    "Late-2018 sell-off": ("2018-10-03", "2018-12-24"),
    "Covid crash": ("2020-02-19", "2020-03-23"),
    "Vaccine rotation": ("2020-11-06", "2020-11-13"),
    "Rate shock": ("2022-01-03", "2022-06-16"),
    "Yen carry unwind": ("2024-07-31", "2024-08-05"),
}
# How the replay works, as crises.json states it.
METHOD = (
    "The book's weights on its last day (value / NAV); each held name's own compounded daily "
    "CRSP return over the window (cache/stress_daily.parquet); a name not trading then takes "
    "the median return of its SIC-2 peers in CRSP size quintile 4, else 0; book = sum of "
    "weight x return. Market = the sum of daily Fama-French Mkt-RF over the window; a "
    "compounded total market return is given beside it. SIC from the organisers' panel at "
    "2026-08-31."
)
# How a name with no trades in a window is filled.
FILL_NOTE = (
    "A name not trading in a window takes the median return of its SIC-2 peers, SIC from "
    "the organisers' panel at 2026-08-31."
)


# The book's weights on its last day, by permno, as shares of NAV.
def last_weights() -> tuple[pd.Timestamp, pd.Series]:
    p = pd.read_parquet(S.RUN / "positions.parquet")
    d = pd.read_parquet(S.RUN / "daily.parquet")
    day = p["date"].max()
    held = p[p["date"] == day].groupby("permno")["value"].sum()
    return day, held / float(d.loc[day, "nav"])


# Each name's filled crisis return, as the stress exhibit builds it.
def filled_returns(w: pd.Series, ep: pd.DataFrame, f0: str, f1: str, info) -> tuple:
    win = ep[(ep["date"] >= f0) & (ep["date"] <= f1)]
    total = (1 + win.pivot_table(index="date", columns="permno", values="ret")).prod() - 1
    st = win[win["date"] == win["date"].min()].drop_duplicates("permno").set_index("permno")
    st["sic2"] = (st["sic"] // 100).astype("Int64")
    st["size"] = pd.qcut(st["cap"].rank(method="first"), 5, labels=False)
    keys = [st["sic2"].reindex(total.index), st["size"].reindex(total.index)]
    peers = total.groupby(keys).median()
    own = total.reindex(w.index)
    covered = own.notna()
    sic2 = (info["sic"].reindex(w.index) // 100).astype("Int64")
    # Our names are all above $300M, the fourth CRSP size quintile.
    fill = [peers.get((s, 3), np.nan) for s in sic2]
    return own.fillna(pd.Series(fill, index=w.index)).fillna(0.0), covered


# Every crisis on one book: market, book, long and short legs.
def replay(w: pd.Series, ep, ff, info) -> list[dict]:
    rows = []
    for label, (f0, f1) in CRISES.items():
        filled, covered = filled_returns(w, ep, f0, f1, info)
        mv = ff.loc[f0:f1]
        lg, sh = w[w > 0], w[w < 0]
        rows.append(
            {
                "crisis": label,
                "first": f0,
                "last": f1,
                "market_pct": float(mv["mktrf"].sum()) * 100,
                "market_compounded_total_pct": float(
                    ((1 + mv["mktrf"] + mv["rf"]).prod() - 1) * 100
                ),
                "book_pct": float((w * filled).sum()) * 100,
                "long_leg_pct_of_nav": float((lg * filled[lg.index]).sum()) * 100,
                "short_leg_pct_of_nav": float((sh * filled[sh.index]).sum()) * 100,
                "longs_avg_stock_return_pct": float((lg * filled[lg.index]).sum() / lg.sum()) * 100,
                "shorts_avg_stock_return_pct": float((sh * filled[sh.index]).sum() / sh.sum())
                * 100,
                "coverage_pct": float(w[covered].abs().sum() / w.abs().sum()) * 100,
            }
        )
    return rows


# One fill's replay with the book's size and the crises' summary.
def summary(day: pd.Timestamp, w: pd.Series, rows: list[dict]) -> dict:
    df = pd.DataFrame(rows)
    return {
        "book_date": str(day.date()),
        "names": int((w != 0).sum()),
        "longs": int((w > 0).sum()),
        "shorts": int((w < 0).sum()),
        "gross_pct": float(w.abs().sum() * 100),
        "net_pct": float(w.sum() * 100),
        "crises": rows,
        "market_mean_pct": float(df["market_pct"].mean()),
        "book_mean_pct": float(df["book_pct"].mean()),
        "long_leg_mean_pct": float(df["long_leg_pct_of_nav"].mean()),
        "short_leg_mean_pct": float(df["short_leg_pct_of_nav"].mean()),
        "book_worst_pct": float(df["book_pct"].min()),
        "book_worst_crisis": df.loc[df["book_pct"].idxmin(), "crisis"],
        "book_best_pct": float(df["book_pct"].max()),
        "book_best_crisis": df.loc[df["book_pct"].idxmax(), "crisis"],
        "crises_book_lost": int((df["book_pct"] < 0).sum()),
        "coverage_mean_pct": float(df["coverage_pct"].mean()),
    }


# The replay of the final book under both fills, to crises.json.
def main() -> None:
    S.DATA.mkdir(parents=True, exist_ok=True)
    ep = pd.read_parquet(S.STRESS)
    ff = pd.read_parquet(S.FF_DAILY)
    ff = ff.assign(date=pd.to_datetime(ff["date"])).set_index("date")
    panel = pd.read_parquet(S.PANEL, columns=["permno", "eom", "sic"])
    panel["eom"] = pd.to_datetime(panel["eom"]) + pd.offsets.MonthEnd(0)
    info = panel[panel["eom"] == DECISION].drop_duplicates("permno").set_index("permno")
    day, w = last_weights()
    out: dict = {"method": METHOD}
    out["peer_fill"] = summary(day, w, replay(w, ep, ff, info))
    frame = pd.DataFrame(out["peer_fill"]["crises"])
    frame.to_csv(S.DATA / "crises_peer_fill.csv", index=False, float_format="%.4f")
    out["fill_note"] = FILL_NOTE
    (S.OUT / "crises.json").write_text(json.dumps(out, indent=1) + "\n")
    got = out["peer_fill"]
    print(f"crises: market {got['market_mean_pct']:.4f}", f"book {got['book_mean_pct']:.4f}")


if __name__ == "__main__":
    main()
