# Writes every v4 exhibit from the final run's tables, once unsealed.

import json
from pathlib import Path

import matplotlib

from fiam.exhibits_v4 import common, extras, required

# How each exhibit reads a PLAN definition the PDF leaves open.
READINGS = {
    "exhibit_1_active_return": "active = strategy cumulative return less the T-bill + 4% "
    "cumulative return, in points; the daily hurdle compounds to the table's monthly bill + 4%",
    "exhibit_2_rolling_beta": "OLS slope of daily excess return on the S&P 500's excess over "
    "252 sessions, as daily_book.book_beta",
    "exhibit_3_calendar_years": "before costs adds back trading and borrow dollars over the "
    "previous NAV (row 9); a year not covered from early January to late December is partial",
    "exhibit_4_exposure_names": "daily closes from the first trade day, as rows 14-16",
    "exhibit_5_top_holdings": "average weight over every session from the first trade, zero "
    "when unheld; labels from the ids table as of each name's last held session",
    "exhibit_6_contributors": "a name's ledger dollars of every kind (price, dividends, "
    "costs, borrow, stubs) over the window, over the starting NAV",
    "exhibit_7_short_liquidity": "holdings dates are the sessions with a trade (row 20); cap "
    "and ADV are each name's latest value at or before the date",
    "exhibit_8_days_of_adv": "days of ADV = |position| / dollar ADV, on every holdings date",
    "extra_k1_fundamental_law": "implied IR = IC x sqrt(breadth) x TC from supplied inputs",
    "extra_capacity": "a planned trade is one name at one formation; held back if any fill "
    "reached 10% of the ADV as of the formation (to 1e-6); days to exit = |position| / (10% ADV)",
    "extra_2026_sub_period": "2026 sessions of the window, compounded, beside the full window",
}


# Draws, checks and saves each exhibit; returns every file written.
def build(tables: dict, out_dir, meta: dict) -> list[Path]:
    x = common.prepare(tables, meta)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written, skipped = [], {}
    for name, draw in required.EXHIBITS + extras.EXTRAS:
        if name == "extra_k1_fundamental_law" and x.k1 is None:
            skipped[name] = "no K1 inputs supplied (ic, breadth, tc by period)"
            continue
        # "$" is text, never mathtext: "$78m to $500m" stays as written.
        with matplotlib.rc_context({"text.parse_math": False}):
            fig, frame = draw(x)
            written += common.save(fig, frame, out, name)
    manifest = {
        "window": [f"{x.first:%Y-%m-%d}", f"{x.last:%Y-%m-%d}"],
        "headline_arm": x.arm,
        "start_nav": x.base,
        "files": sorted(p.name for p in written),
        "skipped": skipped,
        "readings": READINGS,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1))
    return written + [path]
