# The book against CRSP and Compustat: exits, returns, market, report dates. Writes wrds.json.

import json
import sys

import pandas as pd

from fiam import benchmarks as B
from fiam import book as P
from fiam import data, paths

OUT = paths.EXHIBITS / "wrds.json"

# Signals that only move on a report. Book value stands in for be_me, which also moves with price.
ACCOUNTING = ["at_gr1", "niq_su", "ope_be", "o_score", "gp_at", "noa_gr1a", "eqnetis_at", "book"]

# Declared in the plan before the check ran: above this share of early updates, lag and rebuild.
EARLY_LIMIT = 0.01

PERIODS = {"2016_2020": (2016, 2020), "2021_2025": (2021, 2025), "2026": (2026, 2026)}


# The panel's gvkey is a float, Compustat's a zero-padded string, so both meet as the string.
def gvkey(series: pd.Series) -> pd.Series:
    return series.astype("Int64").astype("string").str.zfill(6)


# How every dated exit happened, and what the screen and the payouts did to the book.
def exit_record(table: pd.DataFrame, book: pd.DataFrame, universe: pd.DataFrame) -> dict:
    held = book.join(table, on="PERMNO", how="inner")
    during = held[held["final_month"] == held["Date"]].copy()
    rf = B.benchmarks().set_index("month")["rf"]
    during["payout"] = during["w"] * (during["final_return"] - during["Date"].map(rf))
    months = book["Date"].nunique()

    # Closing a name that left is a trade the backtest already charged, priced here on its own.
    spreads = universe.set_index(["eom", "permno"])["bidaskhl_21d"]
    closing = 0.0
    for date, group in during.groupby("Date"):
        decided = date - pd.offsets.MonthEnd(1)
        weights = group.set_index("PERMNO")["w"]
        own = spreads.xs(decided, level="eom").reindex(weights.index)
        nothing = pd.DataFrame(dict(htb=pd.Series(dtype=bool)))
        parts, _ = P.trading_cost(pd.Series(dtype=float), weights, nothing, own, None)
        closing += sum(parts.values()) - parts["cost_borrow_gc"] - parts["cost_borrow_htb"]

    kind = during["source"].str.replace("CRSP delisting ", "", regex=False).str.strip()
    return dict(
        by_source=table["source"].str.strip().value_counts().to_dict(),
        rows_already_delisted_at_decision_screened=int(universe.attrs.get("dead_at_decision", 0)),
        held_and_already_dead=int(
            (held["exit_date"] <= held["Date"] - pd.offsets.MonthEnd(1)).sum()
        ),
        held_exiting_during_holding_month=dict(
            securities=int(during["PERMNO"].nunique()),
            position_months=int(len(during)),
            by_kind=kind.value_counts().to_dict(),
            long_weight_monthly=float(during["w"].clip(lower=0).sum() / months),
            short_weight_monthly=float(-during["w"].clip(upper=0).sum() / months),
            payout_contribution_annual=float(during["payout"].sum() / months * 12),
            closing_cost_annual_already_charged=float(closing / months * 12),
            what="Names taken over or delisted after the decision. Their final CRSP return is "
            "booked, where booking zero would drop the payout_contribution_annual above.",
        ),
    )


# The panel's next-month return against CRSP's, over the years CRSP covers.
def returns_match(crsp: pd.DataFrame) -> dict:
    panel = data.panel(["ret_exc_lead1m"])
    panel["month"] = panel["eom"] + pd.offsets.MonthBegin(1)
    panel = panel[panel["month"].between("2021-01-01", "2025-12-01")]
    # The panel is in excess of the Ken French cash rate, so the same rate is added back.
    rf = B.french("ff_factors.zip", ["mkt_rf", "smb", "hml", "rf"])["rf"]
    panel["ret"] = panel["ret_exc_lead1m"] + panel["month"].map(rf)
    crsp = crsp.assign(month=pd.to_datetime(crsp["YYYYMM"].astype(str), format="%Y%m"))
    both = panel.merge(
        crsp[["PERMNO", "month", "MthRet"]],
        left_on=["permno", "month"],
        right_on=["PERMNO", "month"],
        how="left",
    )
    pair = both.dropna(subset=["ret", "MthRet"])
    gap = (pair["ret"] - pair["MthRet"]).abs()
    return dict(
        window="2021-01 to 2025-12 holding months",
        panel_rows=int(len(both)),
        compared=int(len(pair)),
        correlation=float(pair["ret"].corr(pair["MthRet"])),
        median_abs_gap=float(gap.median()),
        share_within_1bp=float((gap < 1e-4).mean()),
        share_off_by_over_1pct=float((gap > 0.01).mean()),
        panel_missing_but_crsp_has=int((both["ret"].isna() & both["MthRet"].notna()).sum()),
        crsp_missing_but_panel_has=int((both["ret"].notna() & both["MthRet"].isna()).sum()),
    )


# The book's beta on the S&P 500 with dividends, beside the price-only index the headline uses.
def total_return_market(index: pd.DataFrame) -> dict:
    df = paths.returns()
    index = index.assign(month=pd.to_datetime(index["YYYYMM"].astype(str), format="%Y%m"))
    index = index.set_index("month").sort_index()
    joined = df.join(index[["MthTotRet", "MthPrcRet"]], how="inner").join(B.sp500())
    excess = joined["portfolio_total_return"] - joined["rf"]
    out = dict(
        months=int(len(joined)), window=f"{joined.index.min():%Y-%m} to {joined.index.max():%Y-%m}"
    )
    for name, column in (("total_return_crsp", "MthTotRet"), ("price_only_fred", "sp500")):
        fit = P.regress(excess, joined[column] - joined["rf"])
        out[name] = dict(
            beta=float(fit.params.iloc[1]),
            beta_stderr=float(fit.bse.iloc[1]),
            alpha_annual=float(fit.params.iloc[0] * 12),
            alpha_tstat=float(fit.tvalues.iloc[0]),
        )
    out["dividend_gap_annual"] = float((joined["MthTotRet"] - joined["MthPrcRet"]).mean() * 12)
    out["fred_vs_crsp_price_correlation"] = float(joined["sp500"].corr(joined["MthPrcRet"]))
    return out


# Did any accounting signal change before a report that could have caused it was public?
def release_timing(reports: pd.DataFrame) -> dict:
    columns = ["permno", "gvkey", "eom", "be_me", "me_company", *ACCOUNTING[:-1]]
    panel = data.features(columns)[columns]
    panel = panel[panel["eom"] >= "2015-01-01"].dropna(subset=["gvkey"])
    panel["gvkey"] = gvkey(panel["gvkey"])
    panel["book"] = panel.pop("be_me") * panel.pop("me_company")
    panel = panel.sort_values(["permno", "eom"])

    reports = reports.assign(gvkey=reports["gvkey"].astype("string"))
    reports["release"] = pd.to_datetime(reports["rdq"])
    reports = reports.dropna(subset=["release"]).sort_values("release")[["gvkey", "release"]]
    released = reports.assign(month=reports["release"] + pd.offsets.MonthEnd(0))
    released = released.drop_duplicates(["gvkey", "month"]).set_index(["gvkey", "month"]).index

    out = {}
    for signal in ACCOUNTING:
        before = panel.groupby("permno")[signal].shift()
        # Book value is a product of two floats, so a change is anything past rounding.
        moved = (
            (panel[signal] / before - 1).abs() > 1e-6
            if signal == "book"
            else panel[signal] != before
        )
        updates = panel[moved & before.notna() & panel[signal].notna()][["permno", "gvkey", "eom"]]
        updates = updates.assign(previous=updates.groupby("permno")["eom"].shift()).dropna()
        matched = pd.merge_asof(
            updates.sort_values("eom"), reports, left_on="eom", right_on="release", by="gvkey"
        )
        # Early means no report came out between the last update and this one.
        matched["early"] = ~(matched["release"] > matched["previous"])
        matched["same_day"] = matched["release"] == matched["eom"]
        year = matched["eom"].dt.year
        out[signal] = {
            name: dict(
                updates=int(part.sum()),
                early_share=float(matched.loc[part, "early"].mean()),
                released_on_decision_day_share=float(matched.loc[part, "same_day"].mean()),
            )
            for name, (a, b) in PERIODS.items()
            if (part := year.between(a, b)).any()
        }
    # How often a random firm-month has a release in it, so the matches above are not luck.
    months = panel[panel["eom"] >= "2016-01-01"]
    chance = float(pd.MultiIndex.from_frame(months[["gvkey", "eom"]]).isin(released).mean())
    worst = max(p["early_share"] for s in out.values() for p in s.values())
    return dict(
        rule=f"More than {EARLY_LIMIT:.0%} of a signal's updates before any new report: lag it a "
        "month and rebuild the book. Declared before the check was run.",
        passed=bool(worst <= EARLY_LIMIT),
        worst_early_share=float(worst),
        chance_a_month_has_a_release=chance,
        not_tested="qmj is a rank composite that moves every month; chcsho_12m, ret_12_1 and "
        "ivol_capm_21d come from prices and shares, not reports.",
        signals=out,
    )


# The book again with every update from a report dated on the decision day held back a month.
def release_day_sensitivity(reports: pd.DataFrame) -> dict:
    panel = P.load_panel(extra=("gvkey", "me_company")).sort_values(["permno", "eom"])
    release = pd.to_datetime(reports["rdq"])
    on_month_end = reports.assign(release=release)[release.dt.is_month_end]
    same_day = pd.MultiIndex.from_arrays(
        [on_month_end["gvkey"].astype("string"), on_month_end["release"]]
    )
    flagged = pd.MultiIndex.from_arrays([gvkey(panel["gvkey"]), panel["eom"]]).isin(same_day)
    previous = panel.groupby("permno").shift()
    for signal in [s for s in ACCOUNTING if s in P.SIGNALS]:
        panel.loc[flagged, signal] = previous.loc[flagged, signal]
    # Book-to-market keeps today's price but last month's book value.
    book = previous["be_me"] * previous["me_company"] / panel["me_company"]
    panel.loc[flagged, "be_me"] = book[flagged]

    lagged = P.backtest(P.build_signal(P.screen(panel)))
    return dict(
        what="Accounting updates whose report is dated on the decision day, which may have come "
        "after the close, held back a month. A sensitivity only: the shipped book is unchanged.",
        panel_rows_affected_share=float(flagged.mean()),
        information_ratio=P.information_ratio(lagged["net"]),
        net_annual=float(lagged["net"].mean() * 12),
    )


# The same code on the organizer's data alone, which is what a judge without WRDS rebuilds.
def without_wrds() -> dict:
    universe, trades = P.shipped(P.build_signal(P.screen(P.load_panel(), wrds=False)))
    book = P.backtest(universe, trades=trades)
    stats = P.performance(book)["performance"]
    keep = ("information_ratio", "return_net_annual", "beta_realized", "beta_stderr")
    return {k: float(stats[k]) for k in keep}


# Every WRDS check, written to wrds.json.
def main() -> None:
    exits = data.wrds("exits")
    if exits is None:
        print("skipped: no WRDS exports; add them with uv run run.py --import <folder>")
        return
    crsp = data.wrds("crsp_monthly", ["PERMNO", "YYYYMM", "MthRet"])
    book = paths.holdings()
    book["w"] = book["WEIGHT"] / 100
    universe = P.screen(P.load_panel())
    reports = data.wrds("compustat_quarterly")
    out = dict(
        what="Aggregate checks against CRSP and Compustat. No WRDS row is written here.",
        exits=exit_record(exits, book, universe),
        returns_against_crsp=returns_match(crsp),
        market_with_dividends=total_return_market(data.wrds("sp500_index")),
        report_dates=release_timing(reports),
        release_day_sensitivity=release_day_sensitivity(reports),
        organizer_data_only=without_wrds(),
    )
    OUT.write_text(json.dumps(P.round_floats(out), indent=2), encoding="utf-8", newline="\n")

    r, m, t = out["returns_against_crsp"], out["market_with_dividends"], out["report_dates"]
    print(f"returns: {r['share_within_1bp']:.1%} within 1bp of CRSP, corr {r['correlation']:.4f}")
    total, price = m["total_return_crsp"], m["price_only_fred"]
    print(f"beta with dividends {total['beta']:+.3f}, price only {price['beta']:+.3f}")
    print(f"report dates: worst early share {t['worst_early_share']:.2%}, passed {t['passed']}")
    lagged = out["release_day_sensitivity"]["information_ratio"]
    print(f"release-day updates held back a month: IR {lagged:+.2f}")
    if not t["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
